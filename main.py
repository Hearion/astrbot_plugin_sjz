import httpx
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

@register("sjz", "Hearion", "战备数据查询插件", "1.0.0")
class SjzPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.api_url = "https://www.onebiji.com/hykb_tools/sjzxd/zhanbei/solver/main.php"
        # 金额到地图ID和地图信息的映射（金额单位为万，只取整数）
        self.map_config = {
            11: {"id": 1, "name": "零号大坝/长弓溪谷-机密 零号大坝-水淹", "value": "11.25w"},
            18: {"id": 2, "name": "巴克什/航天基地-机密 零号大坝-永夜", "value": "18.75w"},
            24: {"id": 3, "name": "潮汐监狱-适应", "value": "24.75w"},
            55: {"id": 4, "name": "巴克什-绝密", "value": "55w"},
            60: {"id": 5, "name": "航天基地-绝密", "value": "60w"},
            78: {"id": 6, "name": "潮汐监狱-绝密", "value": "78w"},
        }

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        logger.info("战备数据查询插件已初始化")

    def _format_number(self, value, decimals=0):
        """安全地格式化数字，添加千位分隔符"""
        try:
            if isinstance(value, (int, float)):
                num = float(value)
            elif isinstance(value, str):
                num = float(value)
            else:
                return str(value)
            
            if decimals == 0:
                return f"{int(num):,}"
            else:
                return f"{num:,.{decimals}f}"
        except (ValueError, TypeError):
            return str(value)

    @filter.command("战备")
    async def zhanbei(self, event: AstrMessageEvent):
        """查询战备数据，指令格式：/战备 [金额W]，如：/战备 11W"""
        message_str = event.message_str.strip()
        
        # 解析指令参数
        parts = message_str.split(maxsplit=1)
        if len(parts) < 2:
            available_amounts = "、".join([f"{k}W" for k in self.map_config.keys()])
            yield event.plain_result(f"❌ 请指定要查询的金额\n格式：/战备 [金额W]\n支持金额：{available_amounts}")
            return
        
        # 解析金额参数（支持 11W、11w、11 等格式）
        amount_str = parts[1].upper().replace("W", "").strip()
        try:
            amount = int(amount_str)
            if amount not in self.map_config:
                available_amounts = "、".join([f"{k}W" for k in self.map_config.keys()])
                yield event.plain_result(f"❌ 不支持的金额\n支持金额：{available_amounts}")
                return
        except ValueError:
            available_amounts = "、".join([f"{k}W" for k in self.map_config.keys()])
            yield event.plain_result(f"❌ 请输入有效的金额（整数）\n支持金额：{available_amounts}")
            return
        
        # 获取地图配置
        map_info = self.map_config[amount]
        map_id = map_info["id"]
        
        # 发送 POST 请求
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.api_url,
                    data={
                        "ac": "getRecommendData",
                        "selected_map_id": str(map_id)
                    }
                )
                response.raise_for_status()
                data = response.json()
                
                # 检查返回状态
                if data.get("key") != "ok":
                    yield event.plain_result(f"❌ 查询失败：{data.get('info', '未知错误')}")
                    return
                
                # 解析并格式化数据
                result = self._format_result(data, map_id, map_info)
                yield event.plain_result(result)
                
        except httpx.TimeoutException:
            yield event.plain_result("❌ 请求超时，请稍后重试")
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP 错误: {e}")
            yield event.plain_result(f"❌ 请求失败：HTTP {e.response.status_code}")
        except Exception as e:
            logger.error(f"查询战备数据时发生错误: {e}")
            yield event.plain_result(f"❌ 查询失败：{str(e)}")

    def _format_result(self, data: dict, map_id: int, map_info: dict) -> str:
        """格式化查询结果"""
        result_lines = []
        
        # 标题和基本信息
        result_lines.append("🎯 战备数据查询\n")
        result_lines.append("─" * 42 + "\n")
        result_lines.append(f"📍 地图：{map_info['name']}\n")
        result_lines.append(f"💰 战备值：{map_info['value']}\n")
        result_lines.append("─" * 42 + "\n")
        
        result_data = data.get("data", {})
        target_value = result_data.get("targetValue", "未知")
        target_value_str = self._format_number(target_value)
        result_lines.append(f"🎯 目标数值：{target_value_str}\n")
        result_lines.append("\n")
        
        plans = result_data.get("plans", [])
        if not plans:
            result_lines.append("⚠️ 暂无推荐方案")
            return "".join(result_lines)
        
        # 推荐方案部分
        result_lines.append(f"📋 推荐方案（共 {len(plans)} 个）\n")
        result_lines.append("═" * 42 + "\n")
        result_lines.append("\n")
        
        for idx, plan in enumerate(plans, 1):
            weapon_name = plan.get("weapon_name", "未知武器")
            best_v = plan.get("best_v", 0)
            best_disc_price = plan.get("best_disc_price", 0)
            sum_orig_price = plan.get("_sum_orig_price", 0)
            
            # 方案标题和统计
            result_lines.append(f"【方案 {idx}】{weapon_name}\n")
            result_lines.append("─" * 42 + "\n")
            result_lines.append(f"💵 交易行购入价：{self._format_number(best_disc_price, 2)}\n")
            result_lines.append(f"📊 战备值：{self._format_number(sum_orig_price)}\n")
            result_lines.append("\n")
            
            # 装备清单
            path = plan.get("path", [])
            if path:
                result_lines.append("📦 装备清单：\n")
                
                for item in path:
                    item_name = item.get("name", "未知")
                    item_value = item.get("value", 0)
                    item_disc_price = item.get("disc_price", 0)
                    module_type = item.get("moduleType", "")
                    
                    # 格式化模块类型
                    type_map = {
                        "weapon": "🔫 武器",
                        "helmet": "🪖 头盔",
                        "armor": "🛡️ 防弹衣",
                        "chest": "🎒 胸挂",
                        "bag": "🎒 背包"
                    }
                    type_name = type_map.get(module_type, f"📦 {module_type}")
                    
                    result_lines.append(f"  {type_name}：{item_name}\n")
                    result_lines.append(f"    战备值：{self._format_number(item_value)} | 交易行价格：{self._format_number(item_disc_price, 2)}\n")
                    
                    # 如果有附件，显示附件信息
                    attachments = item.get("attachments", [])
                    if attachments:
                        for att in attachments:
                            att_name = att.get("item", {}).get("name", "未知附件")
                            att_value = att.get("item", {}).get("value", 0)
                            slot_name = att.get("slot_name", "")
                            result_lines.append(f"    └─ {slot_name}：{att_name} (价值：{self._format_number(att_value)})\n")
                    
                    result_lines.append("\n")
            
            # 方案之间的分隔
            if idx < len(plans):
                result_lines.append("═" * 42 + "\n")
                result_lines.append("\n")
        
        return "".join(result_lines)

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        logger.info("战备数据查询插件已卸载")
