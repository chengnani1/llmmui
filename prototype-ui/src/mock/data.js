export const dashboardStats = [
  { label: "已分析应用数", value: 128, unit: "个", accent: "text-blue-700" },
  { label: "权限事件数", value: 3468, unit: "条", accent: "text-slate-900" },
  { label: "交互链数", value: 982, unit: "条", accent: "text-emerald-700" },
  { label: "高风险结果数", value: 54, unit: "项", accent: "text-amber-700" },
];

export const recentTasks = [
  { id: "TASK-20260401-001", appName: "示例出行应用", status: "已完成", time: "2026-04-01 09:10", risk: "中风险" },
  { id: "TASK-20260401-002", appName: "示例社交应用", status: "分析中", time: "2026-04-01 10:25", risk: "待判定" },
  { id: "TASK-20260331-018", appName: "示例购物应用", status: "已完成", time: "2026-03-31 18:42", risk: "高风险" },
  { id: "TASK-20260331-016", appName: "示例办公应用", status: "已完成", time: "2026-03-31 16:05", risk: "低风险" },
];

export const deviceInfo = {
  id: "emulator-5554",
  status: "已连接",
  osVersion: "Android 14",
  model: "Pixel 模拟设备",
  battery: "87%",
};

export const importLogs = [
  { time: "09:12:05", title: "设备连接检测", detail: "识别到 1 台可用测试设备，ADB 通信正常。" },
  { time: "09:13:12", title: "APK 文件校验", detail: "已完成签名结构检查、包名提取与基础信息解析。" },
  { time: "09:14:26", title: "任务创建", detail: "创建任务 TASK-20260401-003，采集模式为标准全量采集。" },
  { time: "09:15:48", title: "交互采集", detail: "正在记录权限请求、按钮点击与页面跳转事件链。" },
];

export const permissionEvents = [
  { id: "EVT-01", name: "位置权限申请", permission: "ACCESS_FINE_LOCATION", severity: "高" },
  { id: "EVT-02", name: "存储读取请求", permission: "READ_EXTERNAL_STORAGE", severity: "中" },
  { id: "EVT-03", name: "通知授权提示", permission: "POST_NOTIFICATIONS", severity: "低" },
  { id: "EVT-04", name: "相机调用行为", permission: "CAMERA", severity: "中" },
];

export const chainSteps = [
  { step: 1, page: "启动页", action: "进入应用", permission: "无", note: "展示欢迎信息与隐私提示。" },
  { step: 2, page: "首页推荐页", action: "点击定位入口", permission: "ACCESS_FINE_LOCATION", note: "用户点击“附近服务”模块。" },
  { step: 3, page: "系统权限弹窗", action: "触发权限申请", permission: "ACCESS_FINE_LOCATION", note: "触发系统级定位权限确认。" },
  { step: 4, page: "位置说明页", action: "阅读权限用途", permission: "ACCESS_FINE_LOCATION", note: "展示定位用途和业务关联说明。" },
  { step: 5, page: "地图结果页", action: "加载附近结果", permission: "ACCESS_FINE_LOCATION", note: "系统返回周边服务结果。" },
];

export const semanticCards = [
  { title: "用户任务", content: "查询当前位置周边服务信息，并根据地图结果继续后续业务操作。" },
  { title: "页面功能", content: "通过首页入口发起位置相关服务检索，调度系统定位能力并返回结果。" },
  { title: "场景描述", content: "场景属于基于地理位置的服务触发链路，权限申请与用户目标具有关联性。" },
  { title: "权限判断", content: "定位权限与页面行为匹配，但说明层级仍可加强，当前判定为中等关注。" },
];

export const resultRows = [
  {
    id: "R-001",
    taskId: "TASK-20260401-001",
    appName: "示例出行应用",
    permission: "ACCESS_FINE_LOCATION",
    level: "高风险",
    excessive: "是",
    duplicated: "否",
    summary: "在未展示充分业务说明前提前申请精准定位权限。",
    chain: "启动页 -> 首页推荐页 -> 系统权限弹窗 -> 地图结果页",
    detail: "系统检测到权限触发时机偏早，用户尚未明确进入定位业务流程，存在过早申请风险。",
  },
  {
    id: "R-002",
    taskId: "TASK-20260401-002",
    appName: "示例社交应用",
    permission: "READ_CONTACTS",
    level: "中风险",
    excessive: "否",
    duplicated: "是",
    summary: "通讯录权限在两个相邻页面重复触发请求。",
    chain: "联系人导入页 -> 推荐好友页 -> 权限弹窗",
    detail: "虽然业务场景相关，但交互链内存在重复请求，影响用户理解与授权体验。",
  },
  {
    id: "R-003",
    taskId: "TASK-20260331-018",
    appName: "示例购物应用",
    permission: "CAMERA",
    level: "低风险",
    excessive: "否",
    duplicated: "否",
    summary: "相机权限仅在扫码功能入口触发，链路清晰。",
    chain: "首页 -> 扫码入口 -> 相机授权弹窗 -> 扫码页",
    detail: "权限申请与扫码任务强相关，说明充分，未发现过度请求现象。",
  },
];

export const historyRows = [
  { id: "H-001", appName: "示例出行应用", permission: "ACCESS_FINE_LOCATION", level: "高风险", date: "2026-04-01", operator: "张研究员" },
  { id: "H-002", appName: "示例社交应用", permission: "READ_CONTACTS", level: "中风险", date: "2026-04-01", operator: "李分析员" },
  { id: "H-003", appName: "示例购物应用", permission: "CAMERA", level: "低风险", date: "2026-03-31", operator: "王分析员" },
  { id: "H-004", appName: "示例办公应用", permission: "READ_EXTERNAL_STORAGE", level: "中风险", date: "2026-03-30", operator: "张研究员" },
  { id: "H-005", appName: "示例教育应用", permission: "RECORD_AUDIO", level: "高风险", date: "2026-03-29", operator: "赵分析员" },
];
