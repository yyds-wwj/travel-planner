"""
高德地图 Web服务 API 客户端

已实现接口:
  1. POI搜索        /v3/place/text       关键字搜索
  2. POI周边搜索    /v3/place/around     坐标周边搜索
  3. 地理编码       /v3/geocode/geo      地址→坐标
  4. 逆地理编码     /v3/geocode/regeo    坐标→地址+周边POI
  5. 距离计算       /v3/distance         多点距离矩阵
  6. 路径规划       /v3/direction/*      驾车/公交/步行/骑行
  7. 天气查询       /v3/weather/weatherInfo  预报+实况
  8. IP定位         /v3/ip                IP→城市
  9. 行政区划       /v3/config/district   城市名→adcode
  10. 输入提示      /v3/assistant/inputtips  模糊地址补全
  11. 交通态势      /v3/traffic/status    实时路况

API文档: https://lbs.amap.com/api/webservice/summary
"""

import os
import json
import hashlib
import urllib.request
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

AMAP_KEY = os.getenv("AMAP_API_KEY", "")
AMAP_SECRET = os.getenv("AMAP_API_SECRET", "")

BASE_URL = "https://restapi.amap.com/v3"


def _sig(params: dict) -> str:
    """生成高德数字签名"""
    if not AMAP_SECRET:
        return ""
    sorted_params = sorted(params.items())
    raw = "&".join(f"{k}={v}" for k, v in sorted_params)
    raw += AMAP_SECRET
    return hashlib.md5(raw.encode()).hexdigest()


def _request(endpoint: str, params: dict) -> dict:
    """发送 GET 请求到高德 API"""
    params["key"] = AMAP_KEY
    if AMAP_SECRET:
        params["sig"] = _sig(params)
    url = f"{BASE_URL}{endpoint}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"status": "0", "info": str(e)}


# ============================================================
# 1. POI 关键字搜索  /v3/place/text
# ============================================================
def search_poi(keywords: str, city: str = "", citylimit: bool = True,
               offset: int = 10, types: str = "") -> dict:
    params = {
        "keywords": keywords,
        "city": city,
        "citylimit": "true" if citylimit else "false",
        "offset": min(offset, 25),
        "extensions": "all",
    }
    if types:
        params["types"] = types
    return _request("/place/text", params)


def search_attractions(city: str, keywords: str = "", offset: int = 15) -> dict:
    """搜索景点、博物馆、美术馆"""
    kw = keywords or "景点"
    return _request("/place/text", {
        "keywords": kw,
        "city": city,
        "types": "风景名胜|博物馆|展览馆|美术馆|纪念馆|公园广场",
        "citylimit": "true",
        "offset": min(offset, 25),
        "extensions": "all",
        "sortrule": "weight",
    })


def search_hotels(city: str, location: str = "", radius: int = 3000,
                  keywords: str = "酒店", offset: int = 10) -> dict:
    """搜索酒店住宿（按城市或按坐标周边）"""
    if location:
        return _request("/place/around", {
            "location": location,
            "keywords": keywords,
            "types": "酒店|宾馆|旅馆|青年旅舍",
            "radius": radius,
            "offset": min(offset, 25),
            "extensions": "all",
        })
    return _request("/place/text", {
        "keywords": keywords,
        "types": "酒店|宾馆|旅馆|青年旅舍",
        "city": city,
        "citylimit": "true",
        "offset": min(offset, 25),
        "extensions": "all",
    })


# ============================================================
# 2. POI 周边搜索  /v3/place/around
# ============================================================
def search_around(location: str, keywords: str = "", radius: int = 3000,
                  types: str = "", offset: int = 10) -> dict:
    params = {
        "location": location,
        "keywords": keywords,
        "radius": radius,
        "offset": min(offset, 25),
        "extensions": "all",
    }
    if types:
        params["types"] = types
    return _request("/place/around", params)


# ============================================================
# 3. 地理编码  /v3/geocode/geo
# 4. 逆地理编码 /v3/geocode/regeo
# ============================================================
def geocode(address: str, city: str = "") -> dict:
    """地址 → 坐标"""
    params = {"address": address}
    if city:
        params["city"] = city
    return _request("/geocode/geo", params)


def regeocode(location: str, extensions: str = "base",
              poitype: str = "", radius: int = 1000) -> dict:
    """
    坐标 → 地址 + 周边信息。

    Args:
        location: "lng,lat"
        extensions: "base"=基本地址, "all"=含周边POI/道路/交叉口
        poitype: 限定返回的POI类型（须 extensions=all），如 "地铁站|公交站"
        radius: POI搜索半径（米），0~3000
    """
    params = {
        "location": location,
        "extensions": extensions,
        "radius": radius,
    }
    if poitype and extensions == "all":
        params["poitype"] = poitype
    return _request("/geocode/regeo", params)


# ============================================================
# 5. 距离计算  /v3/distance
# ============================================================
def distance(origins: str, destination: str, type: int = 1) -> dict:
    """
    距离矩阵计算。
    type: 0=直线距离, 1=驾车, 2=公交, 3=步行
    """
    return _request("/distance", {
        "origins": origins,
        "destination": destination,
        "type": type,
    })


# ============================================================
# 6. 路径规划  /v3/direction/*
# ============================================================
def direction_driving(origin: str, destination: str,
                      strategy: int = 0) -> dict:
    """驾车路径规划"""
    return _request("/direction/driving", {
        "origin": origin,
        "destination": destination,
        "strategy": strategy,
        "extensions": "base",
    })


def direction_transit(origin: str, destination: str,
                      city: str, cityd: str = "") -> dict:
    """公交路径规划"""
    return _request("/direction/transit/integrated", {
        "origin": origin,
        "destination": destination,
        "city": city,
        "cityd": cityd or city,
        "extensions": "base",
    })


def direction_walking(origin: str, destination: str) -> dict:
    """步行路径规划"""
    return _request("/direction/walking", {
        "origin": origin,
        "destination": destination,
    })


def direction_bicycling(origin: str, destination: str) -> dict:
    """骑行路径规划 — 使用 /v4/direction/bicycling"""
    params = {
        "origin": origin,
        "destination": destination,
        "key": AMAP_KEY,
    }
    if AMAP_SECRET:
        params["sig"] = _sig(params)
    url = f"https://restapi.amap.com/v4/direction/bicycling?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"status": "0", "info": str(e)}


# ============================================================
# 6.5 静态地图  /v3/staticmap
# ============================================================
def staticmap(locations: list[dict] = None, zoom: int = 12,
              size: str = "1024*768", scale: int = 1,
              markers: list[dict] = None, labels: list[dict] = None,
              paths: list[dict] = None, traffic: int = 0) -> str:
    """
    生成静态地图图片 URL。

    Args:
        locations: [{"lng": 116.48, "lat": 39.99}, ...] 用于自动计算中心点
        zoom: 缩放级别 [1,17]，默认12（城市级别）
        size: 图片尺寸 "宽*高"，最大 1024*1024
        scale: 1=普通, 2=高清（宽高和zoom加倍）
        markers: 标注列表，每个元素:
            {"lng": x, "lat": y, "size": "mid", "color": "0xFF0000", "label": "A"}
            size: small/mid/large, color: 0xRRGGBB, label: 0-9/A-Z/单个中文
        labels: 文本标签列表，每个元素:
            {"lng": x, "lat": y, "content": "西湖", "fontSize": 12, "color": "0xFFFFFF", "bg": "0x008000"}
        paths: 折线/多边形列表，每个元素:
            {"points": [{"lng":x,"lat":y},...], "weight": 5, "color": "0x0000FF", "transparency": 0.8,
             "fillcolor": "0x0000FF20", "fillTransparency": 0.3}
        traffic: 0=不显示路况, 1=显示实时路况

    Returns:
        完整的静态地图 URL 字符串
    """
    params = {
        "key": AMAP_KEY,
        "zoom": zoom,
        "size": size,
        "scale": scale,
        "traffic": traffic,
    }

    # 自动计算中心点
    if locations:
        lngs = [p["lng"] for p in locations]
        lats = [p["lat"] for p in locations]
        center_lng = (min(lngs) + max(lngs)) / 2
        center_lat = (min(lats) + max(lats)) / 2
        params["location"] = f"{center_lng},{center_lat}"

    # 构建 markers 字符串
    if markers:
        # 按颜色分组
        color_groups: dict[str, list[str]] = {}
        for m in markers:
            color = m.get("color", "0xFC6054")
            size = m.get("size", "mid")
            label = m.get("label", "")
            key_color = f"{size},{color},{label}"
            loc_str = f"{m['lng']},{m['lat']}"
            if key_color not in color_groups:
                color_groups[key_color] = []
            color_groups[key_color].append(loc_str)

        marker_parts = []
        for style, locs in color_groups.items():
            marker_parts.append(f"{style}:{'|'.join(locs)}")
        params["markers"] = "|".join(marker_parts)

    # 构建 labels 字符串
    if labels:
        label_parts = []
        for lb in labels:
            content = lb.get("content", "")[:15]
            font = lb.get("font", 0)
            bold = lb.get("bold", 0)
            size = lb.get("fontSize", 10)
            color = lb.get("color", "0xFFFFFF")
            bg = lb.get("bg", "0x5288d8")
            style = f"{content},{font},{bold},{size},{color},{bg}"
            loc = f"{lb['lng']},{lb['lat']}"
            label_parts.append(f"{style}:{loc}")
        params["labels"] = "|".join(label_parts)

    # 构建 paths 字符串
    if paths:
        path_parts = []
        for p in paths:
            weight = p.get("weight", 5)
            color = p.get("color", "0x0000FF")
            transparency = p.get("transparency", 1)
            fillcolor = p.get("fillcolor", "")
            fill_trans = p.get("fillTransparency", 0.5)
            style = f"{weight},{color},{transparency},{fillcolor},{fill_trans}"
            locs = ";".join(f"{pt['lng']},{pt['lat']}" for pt in p["points"])
            path_parts.append(f"{style}:{locs}")
        params["paths"] = "|".join(path_parts)

    return f"{BASE_URL}/staticmap?{urllib.parse.urlencode(params)}"


def make_attraction_map(attractions: list[dict], hotels: list[dict] = None,
                        zoom: int = 12, size: str = "1024*768") -> str:
    """
    快捷方法：生成景点分布图。

    Args:
        attractions: 景点列表，每个元素有 name, lng, lat（或 coordinates 字段）
        hotels: 酒店列表（可选），每个元素有 name, lng, lat
        zoom: 缩放级别
        size: 图片尺寸
    Returns:
        静态地图 URL
    """
    markers = []
    labels = []
    all_locs = []

    # 景点用红色标记
    for i, a in enumerate(attractions):
        lng = a.get("lng") or (a.get("coordinates", "").split(",")[0] if a.get("coordinates") else None)
        lat = a.get("lat") or (a.get("coordinates", "").split(",")[1] if a.get("coordinates") else None)
        if lng and lat:
            lng, lat = float(lng), float(lat)
            all_locs.append({"lng": lng, "lat": lat})
            markers.append({"lng": lng, "lat": lat, "size": "mid",
                          "color": "0xFF0000", "label": str(i+1)})
            labels.append({"lng": lng, "lat": lat, "content": a.get("name", "")[:8],
                          "fontSize": 10, "color": "0xFFFFFF", "bg": "0xFF0000"})

    # 酒店用蓝色标记
    if hotels:
        for i, h in enumerate(hotels):
            lng = h.get("lng") or (h.get("coordinates", "").split(",")[0] if h.get("coordinates") else None)
            lat = h.get("lat") or (h.get("coordinates", "").split(",")[1] if h.get("coordinates") else None)
            if lng and lat:
                lng, lat = float(lng), float(lat)
                all_locs.append({"lng": lng, "lat": lat})
                markers.append({"lng": lng, "lat": lat, "size": "mid",
                              "color": "0x0000FF", "label": "H"})

    return staticmap(locations=all_locs, zoom=zoom, size=size,
                     markers=markers, labels=labels)


# ============================================================
# 7. 天气查询  /v3/weather/weatherInfo
# ============================================================
# 城市名→adcode 映射（常用旅游城市）
_CITY_ADCODE = {
    "北京": "110000", "上海": "310000", "广州": "440100", "深圳": "440300",
    "杭州": "330100", "成都": "510100", "西安": "610100", "南京": "320100",
    "武汉": "420100", "重庆": "500000", "长沙": "430100", "厦门": "350200",
    "青岛": "370200", "大连": "210200", "苏州": "320500", "昆明": "530100",
    "大理": "532900", "丽江": "530700", "桂林": "450300", "三亚": "460200",
    "拉萨": "540100", "哈尔滨": "230100", "海口": "460100", "贵阳": "520100",
    "张家界": "430800", "黄山": "341000", "洛阳": "410300", "开封": "410200",
    "珠海": "440400", "北海": "450500", "西双版纳": "532800", "香格里拉": "533400",
    "乌鲁木齐": "650100", "呼和浩特": "150100", "银川": "640100", "兰州": "620100",
    "福州": "350100", "南昌": "360100", "合肥": "340100", "郑州": "410100",
    "太原": "140100", "石家庄": "130100", "沈阳": "210100", "长春": "220100",
    "天津": "120000", "济南": "370100", "南宁": "450100",
}


def _resolve_adcode(city: str) -> str:
    """将城市名转换为 adcode"""
    # 先查内置映射
    for name, code in _CITY_ADCODE.items():
        if name in city or city in name:
            return code
    # 调用行政区划 API
    r = district(city)
    if r.get("status") == "1":
        districts = r.get("districts", [])
        if districts:
            return districts[0].get("adcode", city)
    return city  # fallback: 直接用原始值


def weather(city: str, extensions: str = "all") -> dict:
    """
    天气查询。

    Args:
        city: 城市名称（如 "杭州"）或 adcode（如 "330100"）
        extensions: "base"=实况, "all"=预报（未来4天）
    """
    adcode = _resolve_adcode(city)
    return _request("/weather/weatherInfo", {
        "city": adcode,
        "extensions": extensions,
    })


# ============================================================
# 8. IP定位  /v3/ip
# ============================================================
def ip_location(ip: str = "") -> dict:
    """
    IP定位：获取用户当前城市。

    Args:
        ip: IP地址（可空，自动检测请求IP）
    Returns:
        {"status":"1","province":"浙江省","city":"杭州市","adcode":"330100",...}
    """
    params = {}
    if ip:
        params["ip"] = ip
    return _request("/ip", params)


# ============================================================
# 9. 行政区划查询  /v3/config/district
# ============================================================
def district(keywords: str, subdistrict: int = 0) -> dict:
    """城市名 → adcode"""
    return _request("/config/district", {
        "keywords": keywords,
        "subdistrict": subdistrict,
    })


# ============================================================
# 10. 输入提示  /v3/assistant/inputtips
# ============================================================
def input_tips(keywords: str, city: str = "", citylimit: bool = False) -> dict:
    """
    模糊地址自动补全。

    Args:
        keywords: 输入的关键字
        city: 限制城市范围（可选）
        citylimit: 是否仅返回该城市结果
    Returns:
        {"status":"1","tips":[{"name":"...","location":"...","address":"...","adcode":"..."}]}
    """
    params = {
        "keywords": keywords,
        "citylimit": "true" if citylimit else "false",
    }
    if city:
        params["city"] = city
    return _request("/assistant/inputtips", params)


# ============================================================
# 11. 交通态势  /v3/traffic/status
# ============================================================
def traffic_status(location: str = "", rectangle: str = "",
                   level: str = "", extensions: str = "all") -> dict:
    """
    实时交通态势。

    Args:
        location: 中心点坐标 "lng,lat"
        rectangle: 矩形区域 "左下lng,左下lat;右上lng,右上lat"
        level: 道路等级（可选）
        extensions: "all" 返回详细信息
    Returns:
        {"status":"1","trafficinfo":{"evaluation":"...","roads":[...]}}
    """
    params = {"extensions": extensions}
    if rectangle:
        params["rectangle"] = rectangle
    elif location:
        params["location"] = location
    return _request("/traffic/status", params)


# ============================================================
# 辅助格式化函数
# ============================================================

def format_pois(pois: list, max_count: int = 15) -> str:
    """POI列表 → 可读文本"""
    lines = []
    for i, poi in enumerate(pois[:max_count]):
        name = poi.get("name", "未知")
        addr = poi.get("address", "")
        loc = poi.get("location", "")
        biz_ext = poi.get("biz_ext", {})
        deep_info = poi.get("deep_info", {})
        rating = biz_ext.get("rating", deep_info.get("rating", ""))
        cost = biz_ext.get("cost", deep_info.get("cost", ""))
        tel = deep_info.get("tel", biz_ext.get("tel", "")) or poi.get("tel", "")

        lines.append(f"{i+1}. {name}")
        if addr:
            lines.append(f"   地址: {addr}")
        if loc:
            lines.append(f"   坐标: {loc}")
        if rating:
            lines.append(f"   评分: {rating}")
        if cost:
            lines.append(f"   参考价格: {cost}")
        if tel:
            lines.append(f"   电话: {tel}")
        lines.append("")
    return "\n".join(lines) if lines else "未找到结果"


def format_route(route_data: dict) -> str:
    """路径规划结果 → 可读文本"""
    if route_data.get("status") != "1":
        return f"路径规划失败: {route_data.get('info', '未知错误')}"

    route = route_data.get("route", {})
    paths = route.get("paths", [])
    if not paths:
        return "未找到路径"

    result = []
    for i, path in enumerate(paths[:2]):
        distance_km = int(path.get("distance", 0)) / 1000
        duration_min = int(path.get("duration", 0)) / 60
        result.append(f"路线{i+1}: {distance_km:.1f}km, 预计{duration_min:.0f}分钟")

        taxi_cost = path.get("taxi_cost", "")
        if taxi_cost:
            result.append(f"  参考打车费: {taxi_cost}元")

        steps = path.get("steps", [])
        for j, step in enumerate(steps[:8]):
            instruction = step.get("instruction", "")
            if instruction:
                sd = int(step.get("distance", 0))
                st = int(step.get("duration", 0))
                result.append(f"  {j+1}. {instruction} ({sd}m, {st//60}min)")
    return "\n".join(result)


def format_regeocode(regeo_data: dict) -> str:
    """逆地理编码结果 → 可读文本"""
    if regeo_data.get("status") != "1":
        return f"查询失败: {regeo_data.get('info', '未知错误')}"

    rg = regeo_data.get("regeocode", {})
    addr = rg.get("formatted_address", "")
    lines = [f"地址: {addr}"]

    # 周边POI
    pois = rg.get("pois", [])
    if pois:
        lines.append(f"\n周边POI（{len(pois[:10])}个）:")
        for p in pois[:10]:
            name = p.get("name", "")
            ptype = p.get("type", "")
            ploc = p.get("location", "")
            dist = p.get("distance", "")
            if name:
                lines.append(f"  - {name} [{ptype}] 距离{dist}m")
    return "\n".join(lines)


# ============================================================
# 测试
# ============================================================
if __name__ == "__main__":
    if not AMAP_KEY:
        print("错误: 请设置 AMAP_API_KEY")
    else:
        print("=== 景点搜索 ===")
        r = search_attractions("杭州", "西湖", offset=2)
        print(f"结果数: {r.get('count')}, 状态: {r.get('status')}")
        if r.get("pois"):
            print(format_pois(r["pois"][:2]))

        print("=== 天气 (adcode) ===")
        r = weather("杭州")
        print(f"状态: {r.get('status')}")
        if r.get("forecasts"):
            for c in r["forecasts"][0].get("casts", [])[:2]:
                print(f"  {c['date']} {c['dayweather']} {c['nighttemp']}~{c['daytemp']}°C")

        print("=== IP定位 ===")
        r = ip_location()
        print(f"城市: {r.get('city', '')}, adcode: {r.get('adcode', '')}")

        print("=== 逆地理 ===")
        r = regeocode("116.397499,39.908722", extensions="all", poitype="地铁站")
        print(f"状态: {r.get('status')}")
