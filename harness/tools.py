"""
工具定义 — 所有 Agent 共享的工具集。

工具分四类:
1. 通用工具: 所有 Agent 都有的（read_file, write_file, bash）
2. 高德地图工具: 地理数据查询（search_poi, geocode, route, distance, weather）
3. 团队工具: 团队通信专用的（send_message, check_inbox）
4. Lead 专属: 任务管理、团队协调（spawn_teammate, create_task 等）
"""

import json
from pathlib import Path
from harness.message_bus import MessageBus
from harness.task_board import TaskBoard
from harness.agent_loop import WORKSPACE
from harness.amap_client import (
    search_attractions, search_hotels, search_around, search_poi,
    geocode, regeocode, distance,
    direction_driving, direction_transit, direction_walking, direction_bicycling,
    weather, ip_location, input_tips, traffic_status,
    make_attraction_map,
    format_pois, format_route, format_regeocode,
)


# ============================================================
# 通用工具定义 (Tool Schemas)
# ============================================================

READ_FILE_TOOL = {
    "name": "read_file",
    "description": "读取文件内容",
    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "文件路径（相对于工作区）"
            }
        },
        "required": ["file_path"]
    }
}

WRITE_FILE_TOOL = {
    "name": "write_file",
    "description": "写入文件（会覆盖已有内容）",
    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "文件路径（相对于工作区）"
            },
            "content": {
                "type": "string",
                "description": "要写入的内容"
            }
        },
        "required": ["file_path", "content"]
    }
}

BASH_TOOL = {
    "name": "bash",
    "description": "执行 shell 命令（用于搜索、数据处理等）",
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的命令"
            }
        },
        "required": ["command"]
    }
}

# ============================================================
# 高德地图工具
# ============================================================

SEARCH_ATTRACTIONS_TOOL = {
    "name": "search_attractions",
    "description": "在高德地图中搜索景点、博物馆、美术馆。输入城市名称和可选关键字，返回真实的景点列表（含地址、坐标、评分、价格）。",
    "input_schema": {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名称，如 杭州、北京"
            },
            "keywords": {
                "type": "string",
                "description": "可选关键字，如 西湖、博物馆、美术馆"
            },
            "offset": {
                "type": "integer",
                "description": "返回条数，默认15，最大25"
            }
        },
        "required": ["city"]
    }
}

SEARCH_HOTELS_TOOL = {
    "name": "search_hotels",
    "description": "在高德地图中搜索酒店住宿。可按城市搜索或按坐标周边搜索。",
    "input_schema": {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名称"
            },
            "location": {
                "type": "string",
                "description": "周边搜索中心坐标 lng,lat（可选，如 120.15,30.28）"
            },
            "keywords": {
                "type": "string",
                "description": "酒店类型关键字，如 经济型酒店、民宿、青旅"
            }
        },
        "required": ["city"]
    }
}

SEARCH_AROUND_TOOL = {
    "name": "search_around",
    "description": "搜索某坐标周边指定范围内的POI（如搜索景点附近的餐厅、地铁站）。",
    "input_schema": {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "中心点坐标 lng,lat"
            },
            "keywords": {
                "type": "string",
                "description": "搜索关键字，如 地铁站、餐厅、便利店"
            },
            "radius": {
                "type": "integer",
                "description": "搜索半径（米），默认3000"
            },
            "types": {
                "type": "string",
                "description": "POI类型，如 地铁站|公交站"
            }
        },
        "required": ["location", "keywords"]
    }
}

GEOCODE_TOOL = {
    "name": "geocode",
    "description": "将地址转换为坐标（经纬度），或反向查询坐标对应的地址。",
    "input_schema": {
        "type": "object",
        "properties": {
            "address": {
                "type": "string",
                "description": "要查询的地址"
            },
            "city": {
                "type": "string",
                "description": "所在城市（可选，提高精度）"
            }
        },
        "required": ["address"]
    }
}

ROUTE_TOOL = {
    "name": "route",
    "description": "查询两点之间的出行路线（支持驾车、公交地铁、步行、骑行）。返回真实距离、耗时、路线步骤。",
    "input_schema": {
        "type": "object",
        "properties": {
            "origin": {
                "type": "string",
                "description": "起点坐标 lng,lat"
            },
            "destination": {
                "type": "string",
                "description": "终点坐标 lng,lat"
            },
            "type": {
                "type": "string",
                "enum": ["driving", "transit", "walking", "bicycling"],
                "description": "出行方式: driving=驾车, transit=公交地铁, walking=步行, bicycling=骑行"
            },
            "city": {
                "type": "string",
                "description": "城市名称（公交模式必填）"
            }
        },
        "required": ["origin", "destination", "type"]
    }
}

DISTANCE_TOOL = {
    "name": "amap_distance",
    "description": "计算两点或多点之间的驾车/步行距离和时间。",
    "input_schema": {
        "type": "object",
        "properties": {
            "origins": {
                "type": "string",
                "description": "起点坐标 lng,lat（多个用|分隔）"
            },
            "destination": {
                "type": "string",
                "description": "终点坐标 lng,lat"
            },
            "type": {
                "type": "integer",
                "description": "0=直线距离, 1=驾车距离（默认）, 3=步行距离"
            }
        },
        "required": ["origins", "destination"]
    }
}

WEATHER_TOOL = {
    "name": "weather",
    "description": "查询城市天气预报（含未来4天）。",
    "input_schema": {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名称，如 杭州"
            }
        },
        "required": ["city"]
    }
}

REGEOCODE_TOOL = {
    "name": "regeocode",
    "description": "将坐标反向解析为地址描述，同时返回坐标周边的POI（地铁站、餐厅、商场等）。可用于了解某景点附近有什么。",
    "input_schema": {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "坐标 lng,lat"
            },
            "poitype": {
                "type": "string",
                "description": "限定的POI类型，如 地铁站|公交站|餐厅（可选）"
            }
        },
        "required": ["location"]
    }
}

IP_LOCATION_TOOL = {
    "name": "ip_location",
    "description": "通过IP地址获取用户所在城市。不传ip参数时自动检测服务端IP，传入ip参数时定位指定IP。当用户没提供出发城市时调用此工具。",
    "input_schema": {
        "type": "object",
        "properties": {
            "ip": {
                "type": "string",
                "description": "要定位的IP地址（可选，不传则自动检测）"
            }
        },
        "required": []
    }
}

BICYCLING_TOOL = {
    "name": "route_bicycling",
    "description": "查询骑行路线（共享单车/自行车），返回距离、耗时和骑行步骤。适用于景区间短途出行。",
    "input_schema": {
        "type": "object",
        "properties": {
            "origin": {
                "type": "string",
                "description": "起点坐标 lng,lat"
            },
            "destination": {
                "type": "string",
                "description": "终点坐标 lng,lat"
            }
        },
        "required": ["origin", "destination"]
    }
}

TRAFFIC_TOOL = {
    "name": "traffic_status",
    "description": "查询实时交通态势，了解道路拥堵情况。",
    "input_schema": {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "中心点坐标 lng,lat"
            },
            "rectangle": {
                "type": "string",
                "description": "矩形区域 左下lng,lat;右上lng,lat（可选，与location二选一）"
            }
        },
        "required": []
    }
}

INPUT_TIPS_TOOL = {
    "name": "input_tips",
    "description": "模糊地址自动补全。当你只有部分地址信息时，用此工具获取完整地址建议和坐标。",
    "input_schema": {
        "type": "object",
        "properties": {
            "keywords": {
                "type": "string",
                "description": "输入的模糊地址关键字，如 西湖区龙井路"
            },
            "city": {
                "type": "string",
                "description": "限制城市范围（可选），如 杭州"
            }
        },
        "required": ["keywords"]
    }
}

STATIC_MAP_TOOL = {
    "name": "generate_map",
    "description": "生成景点和酒店的静态地图图片URL。传入景点和酒店列表（含坐标），自动生成带标注和标签的地图。将返回的URL嵌入最终攻略即可展示可视化地图。",
    "input_schema": {
        "type": "object",
        "properties": {
            "attractions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "景点名称"},
                        "lng": {"type": "number", "description": "经度"},
                        "lat": {"type": "number", "description": "纬度"}
                    }
                },
                "description": "景点列表（含坐标）"
            },
            "hotels": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "酒店名称"},
                        "lng": {"type": "number", "description": "经度"},
                        "lat": {"type": "number", "description": "纬度"}
                    }
                },
                "description": "酒店列表（可选）"
            },
            "zoom": {
                "type": "integer",
                "description": "缩放级别 1-17，默认12"
            }
        },
        "required": ["attractions"]
    }
}

# 所有高德工具列表（给专家 Agent 使用）
AMAP_TOOLS = [
    SEARCH_ATTRACTIONS_TOOL,
    SEARCH_HOTELS_TOOL,
    SEARCH_AROUND_TOOL,
    GEOCODE_TOOL,
    REGEOCODE_TOOL,
    ROUTE_TOOL,
    BICYCLING_TOOL,
    DISTANCE_TOOL,
    WEATHER_TOOL,
    TRAFFIC_TOOL,
    INPUT_TIPS_TOOL,
    STATIC_MAP_TOOL,
]


# ============================================================
# 团队通信工具
# ============================================================

SEND_MESSAGE_TOOL = {
    "name": "send_message",
    "description": "向其他 Agent 发送消息",
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "目标 Agent 名称"
            },
            "content": {
                "type": "string",
                "description": "消息内容"
            },
            "msg_type": {
                "type": "string",
                "enum": ["message", "result", "plan_request", "info_request"],
                "description": "消息类型"
            }
        },
        "required": ["to", "content"]
    }
}

CHECK_INBOX_TOOL = {
    "name": "check_inbox",
    "description": "检查自己的收件箱",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

# ============================================================
# Lead 专属：任务管理工具
# ============================================================

CREATE_TASK_TOOL = {
    "name": "create_task",
    "description": "在任务看板上创建新任务",
    "input_schema": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "任务 ID（如 task_01）"
            },
            "subject": {
                "type": "string",
                "description": "任务标题"
            },
            "description": {
                "type": "string",
                "description": "任务详细描述"
            },
            "blocked_by": {
                "type": "array",
                "items": {"type": "string"},
                "description": "前置任务 ID 列表"
            }
        },
        "required": ["task_id", "subject", "description"]
    }
}

LIST_TASKS_TOOL = {
    "name": "list_tasks",
    "description": "查看任务看板上的所有任务",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

SPAWN_TEAMMATE_TOOL = {
    "name": "spawn_teammate",
    "description": "启动一个专家 Agent 队友",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Agent 名称（如 attraction_expert）"
            },
            "role": {
                "type": "string",
                "description": "角色描述（如 景点美术推荐专家）"
            },
            "prompt": {
                "type": "string",
                "description": "给专家的初始任务描述"
            }
        },
        "required": ["name", "role", "prompt"]
    }
}

REQUEST_SHUTDOWN_TOOL = {
    "name": "request_shutdown",
    "description": "请求某个专家 Agent 关机",
    "input_schema": {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "要关机的 Agent 名称"
            }
        },
        "required": ["target"]
    }
}


# ============================================================
# 工具处理器工厂
# ============================================================

def make_handlers(bus: MessageBus, board: TaskBoard, agent_name: str,
                  spawn_fn: callable = None) -> dict:
    """为指定 Agent 创建工具处理函数。

    Args:
        bus: 消息总线
        board: 任务看板
        agent_name: 当前 Agent 名称
        spawn_fn: Lead 的 spawn_teammate 实现（专家 Agent 不需要）

    Returns:
        工具名 → 处理函数 的映射
    """

    def handle_read_file(params: dict) -> str:
        file_path = WORKSPACE / params["file_path"]
        if not file_path.exists():
            return f"File not found: {params['file_path']}"
        return file_path.read_text(encoding="utf-8")

    def handle_write_file(params: dict) -> str:
        file_path = WORKSPACE / params["file_path"]
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(params["content"], encoding="utf-8")
        return f"Written: {params['file_path']} ({len(params['content'])} chars)"

    def handle_bash(params: dict) -> str:
        import subprocess
        import locale
        try:
            result = subprocess.run(
                params["command"], shell=True, capture_output=True, text=True,
                timeout=30, cwd=str(WORKSPACE),
                encoding="utf-8", errors="replace",  # UTF-8 + 非法字符替换
            )
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            # 如果 UTF-8 解析后全是乱码（替换字符过多），尝试用系统编码
            if stdout.count('\ufffd') > len(stdout) * 0.3:
                try:
                    sys_enc = locale.getpreferredencoding()
                    result2 = subprocess.run(
                        params["command"], shell=True, capture_output=True, text=True,
                        timeout=30, cwd=str(WORKSPACE), encoding=sys_enc, errors="replace",
                    )
                    stdout = result2.stdout or ""
                except Exception:
                    pass
            return stdout or stderr or "(no output)"
        except subprocess.TimeoutExpired:
            return "Command timed out (30s)"

    def handle_send_message(params: dict) -> str:
        bus.send(
            from_agent=agent_name,
            to_agent=params["to"],
            content=params["content"],
            msg_type=params.get("msg_type", "message"),
        )
        return f"Message sent to {params['to']}"

    def handle_check_inbox(params: dict) -> str:
        msgs = bus.read_inbox(agent_name)
        if not msgs:
            return "Inbox empty."
        lines = []
        for m in msgs:
            lines.append(f"[{m.msg_type}] From {m.msg_from}: {m.content[:300]}")
        return "\n".join(lines)

    # --- 高德地图工具处理函数 ---

    def handle_search_attractions(params: dict) -> str:
        r = search_attractions(
            city=params["city"],
            keywords=params.get("keywords", ""),
            offset=params.get("offset", 15),
        )
        if r.get("status") != "1":
            return f"搜索失败: {r.get('info', '未知错误')}"
        count = r.get("count", 0)
        pois = r.get("pois", [])
        return f"找到 {count} 个结果:\n{format_pois(pois)}"

    def handle_search_hotels(params: dict) -> str:
        r = search_hotels(
            city=params["city"],
            location=params.get("location", ""),
            keywords=params.get("keywords", "酒店"),
        )
        if r.get("status") != "1":
            return f"搜索失败: {r.get('info', '未知错误')}"
        count = r.get("count", 0)
        pois = r.get("pois", [])
        return f"找到 {count} 个酒店:\n{format_pois(pois)}"

    def handle_search_around(params: dict) -> str:
        r = search_around(
            location=params["location"],
            keywords=params.get("keywords", ""),
            radius=params.get("radius", 3000),
            types=params.get("types", ""),
        )
        if r.get("status") != "1":
            return f"周边搜索失败: {r.get('info', '未知错误')}"
        count = r.get("count", 0)
        pois = r.get("pois", [])
        return f"周边找到 {count} 个结果:\n{format_pois(pois)}"

    def handle_geocode(params: dict) -> str:
        r = geocode(
            address=params["address"],
            city=params.get("city", ""),
        )
        if r.get("status") != "1":
            return f"地理编码失败: {r.get('info', '未知错误')}"
        geocodes = r.get("geocodes", [])
        if not geocodes:
            return "未找到匹配坐标"
        lines = []
        for g in geocodes[:5]:
            lines.append(f"{g.get('formatted_address', '')} → {g.get('location', '')}")
        return "\n".join(lines)

    def handle_route(params: dict) -> str:
        origin = params["origin"]
        destination = params["destination"]
        route_type = params["type"]
        city = params.get("city", "")
        if route_type == "driving":
            r = direction_driving(origin, destination)
        elif route_type == "transit":
            r = direction_transit(origin, destination, city)
        elif route_type == "walking":
            r = direction_walking(origin, destination)
        elif route_type == "bicycling":
            r = direction_bicycling(origin, destination)
        else:
            return f"不支持的出行方式: {route_type}"
        return format_route(r)

    def handle_amap_distance(params: dict) -> str:
        r = distance(
            origins=params["origins"],
            destination=params["destination"],
            type=params.get("type", 1),
        )
        if r.get("status") != "1":
            return f"距离计算失败: {r.get('info', '未知错误')}"
        results = r.get("results", [])
        lines = []
        for d in results:
            dist_km = int(d.get("distance", 0)) / 1000
            dur_min = int(d.get("duration", 0)) / 60
            lines.append(f"距离: {dist_km:.1f}km, 预计耗时: {dur_min:.0f}分钟")
        return "\n".join(lines)

    def handle_weather(params: dict) -> str:
        r = weather(city=params["city"], extensions="all")
        if r.get("status") != "1":
            return f"天气查询失败: {r.get('info', '未知错误')}"
        forecasts = r.get("forecasts", [])
        if not forecasts:
            return "未找到天气数据"
        f = forecasts[0]
        lines = [f"城市: {f.get('city', '')}"]
        for cast in f.get("casts", []):
            lines.append(
                f"  {cast.get('date')} {cast.get('week')} "
                f"{cast.get('dayweather')}/{cast.get('nightweather')} "
                f"{cast.get('nighttemp')}°C~{cast.get('daytemp')}°C "
                f"{cast.get('daywind')}"
            )
        return "\n".join(lines)

    def handle_regeocode(params: dict) -> str:
        r = regeocode(
            location=params["location"],
            extensions="all",
            poitype=params.get("poitype", ""),
        )
        return format_regeocode(r)

    def handle_ip_location(params: dict) -> str:
        r = ip_location(ip=params.get("ip", ""))
        if r.get("status") != "1":
            return f"IP定位失败: {r.get('info', '未知错误')}（如果是本地运行，IP定位无法生效，请直接询问用户出发城市）"
        city = r.get('city', '')
        if not city:
            return "IP定位未获取到城市（可能是局域网环境），请直接询问用户出发城市。"
        return (f"当前城市: {city}\n"
                f"省份: {r.get('province', '')}\n"
                f"adcode: {r.get('adcode', '')}")

    def handle_route_bicycling(params: dict) -> str:
        r = direction_bicycling(params["origin"], params["destination"])
        return format_route(r)

    def handle_traffic(params: dict) -> str:
        r = traffic_status(
            location=params.get("location", ""),
            rectangle=params.get("rectangle", ""),
        )
        if r.get("status") != "1":
            return f"交通态势查询失败: {r.get('info', '未知错误')}"
        info = r.get("trafficinfo", {})
        evaluation = info.get("evaluation", "")
        desc = info.get("description", "")
        roads = info.get("roads", [])[:10]
        lines = []
        if evaluation:
            lines.append(f"整体路况: {evaluation}")
        if desc:
            lines.append(f"描述: {desc}")
        for road in roads:
            name = road.get("name", "")
            status = road.get("status", "")
            speed = road.get("speed", "")
            direction = road.get("direction", "")
            if name:
                lines.append(f"  {name}: {status} (速度:{speed}km/h 方向:{direction})")
        return "\n".join(lines) if lines else "无路况数据"

    def handle_input_tips(params: dict) -> str:
        r = input_tips(
            keywords=params["keywords"],
            city=params.get("city", ""),
        )
        if r.get("status") != "1":
            return f"输入提示查询失败: {r.get('info', '未知错误')}"
        tips = r.get("tips", [])[:10]
        if not tips:
            return "未找到匹配结果"
        lines = [f"'{params['keywords']}' 的匹配结果:"]
        for t in tips:
            name = t.get("name", "")
            addr = t.get("address", "")
            loc = t.get("location", "")
            if name:
                lines.append(f"  - {name} | {addr or ''} | {loc or ''}")
        return "\n".join(lines)

    def handle_generate_map(params: dict) -> str:
        attractions = []
        for a in params.get("attractions", []):
            attractions.append({
                "name": a.get("name", ""),
                "lng": a.get("lng"),
                "lat": a.get("lat"),
            })
        hotels = []
        for h in params.get("hotels", []):
            hotels.append({
                "name": h.get("name", ""),
                "lng": h.get("lng"),
                "lat": h.get("lat"),
            })
        zoom = params.get("zoom", 12)
        url = make_attraction_map(attractions, hotels, zoom=zoom)
        return f"静态地图已生成，将以下 URL 嵌入攻略即可:\n\n![景点地图]({url})"

    def handle_list_tasks(params: dict) -> str:
        return board.summary()

    def handle_create_task(params: dict) -> str:
        from harness.task_board import Task
        task = Task(
            id=params["task_id"],
            subject=params["subject"],
            description=params["description"],
            blocked_by=params.get("blocked_by", []),
        )
        board.create_task(task)
        return f"Task created: {task.id} - {task.subject}"

    handlers = {
        "read_file": handle_read_file,
        "write_file": handle_write_file,
        "bash": handle_bash,
        "send_message": handle_send_message,
        "check_inbox": handle_check_inbox,
        # --- 高德地图工具 ---
        "search_attractions": handle_search_attractions,
        "search_hotels": handle_search_hotels,
        "search_around": handle_search_around,
        "geocode": handle_geocode,
        "regeocode": handle_regeocode,
        "route": handle_route,
        "route_bicycling": handle_route_bicycling,
        "amap_distance": handle_amap_distance,
        "weather": handle_weather,
        "traffic_status": handle_traffic,
        "input_tips": handle_input_tips,
        "generate_map": handle_generate_map,
    }

    # Lead 独有工具
    if spawn_fn:
        handlers["ip_location"] = handle_ip_location

    # Lead 独有的工具
    if spawn_fn:
        handlers["list_tasks"] = handle_list_tasks
        handlers["create_task"] = handle_create_task

        def handle_spawn_teammate(params: dict) -> str:
            return spawn_fn(params["name"], params["role"], params["prompt"])
        handlers["spawn_teammate"] = handle_spawn_teammate

        def handle_request_shutdown(params: dict) -> str:
            from harness.team_protocols import ProtocolManager
            return f"Shutdown requested for {params['target']}"
        handlers["request_shutdown"] = handle_request_shutdown

    return handlers
