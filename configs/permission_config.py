# -*- coding: utf-8 -*-
"""
权限识别配置：危险权限全集 & 文本匹配规则表
"""

from typing import Dict, List

# ========================= 权限全集 =========================
ALL_DANGEROUS_PERMS: List[str] = [
    "READ_CALENDAR", "WRITE_CALENDAR",
    "READ_CALL_LOG", "WRITE_CALL_LOG",
    "PROCESS_OUTGOING_CALLS",
    "CAMERA",
    "READ_CONTACTS", "WRITE_CONTACTS",
    "GET_ACCOUNTS",
    "ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION",
    "ACCESS_BACKGROUND_LOCATION",
    "RECORD_AUDIO",
    "READ_PHONE_STATE", "READ_PHONE_NUMBERS",
    "CALL_PHONE", "ANSWER_PHONE_CALLS",
    "ADD_VOICEMAIL",
    "USE_SIP",
    "ACCEPT_HANDOVER",
    "BODY_SENSORS",
    "SEND_SMS", "RECEIVE_SMS", "READ_SMS",
    "RECEIVE_WAP_PUSH", "RECEIVE_MMS",
    "READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE",
    "ACCESS_MEDIA_LOCATION",
    "ACTIVITY_RECOGNITION",
]

# ========================= 权限规则表 =========================
# 这里用 “授权文案中的中文 substring” → “权限列表”
BASE_PERMISSION_TABLE: Dict[str, Dict[str, List[str]]] = {
    "MI": {
        "通过网络或者卫星对您的手机定位": [
            "ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION"
        ],
        "允许后台访问位置信息": ["ACCESS_BACKGROUND_LOCATION"],
        "访问您设备上的照片、媒体内容和文件": [
            "READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE"
        ],
        "读写设备上的照片及文件": [
            "READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE"
        ],
        "读取设备上的照片及文件": [
            "READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE"
        ],
        "读取照片位置信息": ["ACCESS_MEDIA_LOCATION"],
        "获取手机号码、IMEI、IMSI权限": [
            "READ_PHONE_STATE", "READ_PHONE_NUMBERS"
        ],
        "获取手机号": [
            "READ_PHONE_STATE", "READ_PHONE_NUMBERS"
        ],
        "读取通话记录": ["READ_CALL_LOG"],
        "写入/删除通话记录": ["WRITE_CALL_LOG"],
        "直接拨打电话": ["CALL_PHONE"],
        "接听、监听、挂断电话": ["ANSWER_PHONE_CALLS"],
        "监控呼出电话": ["PROCESS_OUTGOING_CALLS"],
        "使用SIP视频服务": ["USE_SIP"],
        "继续进行来自其他App的通话": ["ACCEPT_HANDOVER"],
        "添加语音邮件": ["ADD_VOICEMAIL"],
        "拍摄照片和录制视频": ["CAMERA"],
        "录制音频": ["RECORD_AUDIO"],
        "读取联系人": ["READ_CONTACTS"],
        "写入/删除联系人": ["WRITE_CONTACTS"],
        "获取手机的账户列表": ["GET_ACCOUNTS"],
        "访问您的日历": ["READ_CALENDAR", "WRITE_CALENDAR"],
        "读取短信": ["READ_SMS"],
        "接收短信": ["RECEIVE_SMS"],
        "发送短信": ["SEND_SMS"],
        "接收WAP推送": ["RECEIVE_WAP_PUSH"],
        "接收彩信": ["RECEIVE_MMS"],
        "识别身体活动": ["ACTIVITY_RECOGNITION"],
        "访问身体传感器": ["BODY_SENSORS"],
    },

    "HUAWEI": {
        "获取此设备的位置信息": [
            "ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION"
        ],
        "允许应用在后台访问位置信息": ["ACCESS_BACKGROUND_LOCATION"],
        "访问设备上的照片、媒体内容和文件": [
            "READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE"
        ],
        "读取照片和视频的位置信息": ["ACCESS_MEDIA_LOCATION"],
        "获取设备信息": [
            "READ_PHONE_STATE", "READ_PHONE_NUMBERS"
        ],
        "拨打电话": ["CALL_PHONE"],
        "读取通话记录": ["READ_CALL_LOG"],
        "新建/修改/删除通话记录": ["WRITE_CALL_LOG"],
        "接听电话": ["ANSWER_PHONE_CALLS"],
        "继续进行来自其他应用的通话": ["ACCEPT_HANDOVER"],
        "添加语音邮件": ["ADD_VOICEMAIL"],
        "使用网络电话": ["USE_SIP"],
        "拍摄照片或录制视频": ["CAMERA"],
        "录制音频": ["RECORD_AUDIO"],
        "读取联系人": ["READ_CONTACTS"],
        "新增/修改/删除联系人": ["WRITE_CONTACTS"],
        "获取手机的账户列表": ["GET_ACCOUNTS"],
        "读取日历": ["READ_CALENDAR"],
        "新建/修改/删除日历": ["WRITE_CALENDAR"],
        "访问您的健身运动": ["ACTIVITY_RECOGNITION"],
        "访问与您身体状况相关的传感器数据": ["BODY_SENSORS"],
        "读取短信": ["READ_SMS"],
        "接收短信": ["RECEIVE_SMS"],
        "发送短信": ["SEND_SMS"],
        "接收WAP推送": ["RECEIVE_WAP_PUSH"],
        "接收彩信": ["RECEIVE_MMS"],
    },
}