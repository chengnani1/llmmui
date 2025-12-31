import json
import os

# 输入文件路径
input_path = "/Volumes/Charon/data/work/llm/code/Android/permission_map.json"
output_path = "/Volumes/Charon/data/work/llm/code/Android/permission_map_en.json"

# 中文 → 英文映射表
scene_translate = {
    "地图导航": "Maps and Navigation",
    "打车服务": "Ride-Hailing Services",
    "即时通信聊天服务": "Instant Messaging",
    "电话通话": "Phone Calls",
    "网络社区": "Online Communities",
    "网络支付": "Online Payments",
    "网上购物": "E-Commerce",
    "餐饮外卖": "Food Delivery",
    "邮寄服务": "Mail and Parcel Services",
    "交通票务": "Transportation Ticketing",
    "婚恋相亲": "Dating and Matchmaking",
    "求职招聘": "Job Recruitment",
    "网络借贷": "Online Lending",
    "房屋租售": "Housing Rentals and Sales",
    "汽车交易": "Automobile Trading",
    "医疗健康": "Medical and Health",
    "旅游服务": "Travel Services",
    "酒店预定": "Hotel Booking",
    "网络游戏": "Online Gaming",
    "学习教育": "Education and Learning",
    "维修装修": "Home Repair and Renovation",
    "女性健康": "Women's Health",
    "汽车单车租赁": "Car and Bike Rental",
    "投资理财": "Investment and Finance",
    "手机银行": "Mobile Banking",
    "网络邮箱": "Email Services",
    "远程会议": "Remote Conferencing",
    "网络直播": "Live Streaming",
    "在线影音": "Online Video and Audio",
    "新闻资讯": "News and Information",
    "运动健身": "Sports and Fitness",
    "浏览器": "Web Browsers",
    "杀毒软件": "Antivirus Software",
    "电子图书": "E-Books",
    "拍摄美化": "Photography and Beautification",
    "应用商店": "App Store",
    "天气": "Weather",
    "日历": "Calendar",
    "实用工具": "Utility Tools",
    "文件管理": "File Management",
    "娱乐票务": "Entertainment Ticketing",
    "用户登录": "User Login",
    "其他": "Others",
    "广告": "Advertising",
}

def translate_keys(data: dict) -> dict:
    """将 map 的 key 从中文翻译为英文"""
    new_map = {}
    for cn_key, value in data.items():
        en_key = scene_translate.get(cn_key, cn_key)  # 找不到翻译则保持原样
        new_map[en_key] = value
    return new_map


def main():
    if not os.path.exists(input_path):
        print(f"Input file not found: {input_path}")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        pm = json.load(f)

    # 翻译两个映射表
    pm_en = {
        "allowed_map": translate_keys(pm.get("allowed_map", {})),
        "banned_map": translate_keys(pm.get("banned_map", {})),
    }

    # 输出英文版 JSON
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(pm_en, f, ensure_ascii=False, indent=4)

    print("Finished! Saved to:", output_path)


if __name__ == "__main__":
    main()