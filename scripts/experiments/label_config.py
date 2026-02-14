# ---------------------------------------------------------
# 场景列表（编号 1~44）
# ---------------------------------------------------------
SCENE_LIST = [
    "地图导航", "打车服务", "即时通信聊天服务", "电话通话", "网络社区", "网络支付",
    "网上购物", "餐饮外卖", "邮寄服务", "交通票务", "婚恋相亲", "求职招聘",
    "网络借贷", "房屋租售", "汽车交易", "医疗健康", "旅游服务", "酒店预定",
    "网络游戏", "学习教育", "维修装修", "女性健康", "汽车单车租赁", "投资理财",
    "手机银行", "网络邮箱", "远程会议", "网络直播", "在线影音", "新闻资讯",
    "运动健身", "浏览器", "杀毒软件", "电子图书", "拍摄美化", "应用商店",
    "天气", "日历", "实用工具", "文件管理", "娱乐票务", "用户登录",
    "其他", "广告","个人信息"
]

# ---------------------------------------------------------
# 权限候选（编号形式展示 + 中文解释）
# ---------------------------------------------------------
PERMISSION_CANDIDATES = [
    "READ_CALENDAR",              #1 读取日历
    "WRITE_CALENDAR",             #2 编辑日历
    "READ_CALL_LOG",              #3 读取通话记录
    "WRITE_CALL_LOG",             #4 编辑通话记录
    "PROCESS_OUTGOING_CALLS",     #5 监控呼出电话
    "CAMERA",                     #6 拍摄
    "READ_CONTACTS",              #7 读取通讯录
    "WRITE_CONTACTS",             #8 编辑通讯录
    "GET_ACCOUNTS",               #9 获取 App 账户
    "ACCESS_FINE_LOCATION",       #10 访问精准定位
    "ACCESS_COARSE_LOCATION",     #11 访问粗略位置
    "ACCESS_BACKGROUND_LOCATION", #12 后台访问位置
    "RECORD_AUDIO",               #13 录音
    "READ_PHONE_STATE",           #14 读取电话状态
    "READ_PHONE_NUMBERS",         #15 读取本机电话号码
    "CALL_PHONE",                 #16 拨打电话
    "ANSWER_PHONE_CALLS",         #17 接听电话
    "ADD_VOICEMAIL",              #18 添加语音邮件
    "USE_SIP",                    #19 使用网络电话
    "ACCEPT_HANDOVER",            #20 继续其他 App 的通话
    "BODY_SENSORS",               #21 身体传感器
    "SEND_SMS",                   #22 发送短信
    "RECEIVE_SMS",                #23 接收短信
    "READ_SMS",                   #24 读取短信
    "RECEIVE_WAP_PUSH",           #25 接收 WAP 推送
    "RECEIVE_MMS",                #26 接收彩信
    "READ_EXTERNAL_STORAGE",      #27 读取存储
    "WRITE_EXTERNAL_STORAGE",     #28 写入存储
    "ACCESS_MEDIA_LOCATION",      #29 读取照片位置信息
    "ACTIVITY_RECOGNITION",       #30 识别身体活动
]