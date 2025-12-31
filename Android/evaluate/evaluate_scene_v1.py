import os
import json
from collections import defaultdict
from tqdm import tqdm #type: ignore

SCENE_LIST = [
    "地图导航", "打车服务", "即时通信聊天服务", "电话通话", "网络社区", "网络支付",
    "网上购物", "餐饮外卖", "邮寄服务", "交通票务", "婚恋相亲", "求职招聘",
    "网络借贷", "房屋租售", "汽车交易", "医疗健康", "旅游服务", "酒店预定",
    "网络游戏", "学习教育", "维修装修", "女性健康", "汽车单车租赁", "投资理财",
    "手机银行", "网络邮箱", "远程会议", "网络直播", "在线影音", "新闻资讯",
    "运动健身", "浏览器", "杀毒软件", "电子图书", "拍摄美化", "应用商店",
    "天气", "日历", "实用工具", "文件管理", "娱乐票务", "用户登录",
    "其他", "广告"
]

def evaluate_single_app(app_dir):
    """
    对一个 APP 的场景识别进行评测
    """
    scene_pred_path = os.path.join(app_dir, "results_scene.json")
    scene_label_path = os.path.join(app_dir, "scene_labels.json")

    if not os.path.exists(scene_pred_path) or not os.path.exists(scene_label_path):
        print(f"⚠ 缺少预测或标签文件：{app_dir}")
        return None

    preds = json.load(open(scene_pred_path, "r"))
    labels = json.load(open(scene_label_path, "r"))

    total = len(labels)
    top1_correct = 0
    top3_correct = 0

    per_scene_stats = defaultdict(lambda: {"total": 0, "top1": 0, "top3": 0})

    for label_item, pred_item in zip(labels, preds):
        true_scene = label_item["true_scene"]
        pred_top1 = pred_item["scene"]["top1"]
        pred_top3 = pred_item["scene"]["top3"]

        per_scene_stats[true_scene]["total"] += 1

        if pred_top1 == true_scene:
            top1_correct += 1
            per_scene_stats[true_scene]["top1"] += 1

        if true_scene in pred_top3:
            top3_correct += 1
            per_scene_stats[true_scene]["top3"] += 1

    return {
        "app": os.path.basename(app_dir),
        "total": total,
        "top1_acc": top1_correct / total,
        "top3_acc": top3_correct / total,
        "per_scene": per_scene_stats
    }


def evaluate_all(processed_root):
    """
    遍历所有 fastbot-* 目录进行评测
    """
    app_dirs = [
        os.path.join(processed_root, d)
        for d in os.listdir(processed_root)
        if d.startswith("fastbot-")
    ]

    all_results = []

    for app_dir in tqdm(app_dirs, desc="评测 APP"):
        r = evaluate_single_app(app_dir)
        if r:
            all_results.append(r)

    # 汇总 overall
    total_chains = sum(r["total"] for r in all_results)
    top1 = sum(r["top1_acc"] * r["total"] for r in all_results)
    top3 = sum(r["top3_acc"] * r["total"] for r in all_results)

    overall = {
        "total_chains": total_chains,
        "overall_top1_acc": top1 / total_chains,
        "overall_top3_acc": top3 / total_chains,
        "apps": all_results
    }

    json.dump(overall, open("evaluation_scene.json", "w"), indent=2, ensure_ascii=False)
    print("✔ 场景识别评测完成，输出 evaluation_scene.json")


if __name__ == "__main__":
    import sys
    evaluate_all(sys.argv[1])