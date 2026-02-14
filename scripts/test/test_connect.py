import requests

url = "http://127.0.0.1:8010/v1/chat/completions"

payload = {
    "model": "/home/fanm/zxc/model/Qwen2.5-VL-32B-Instruct",
    "messages": [
        {"role": "user", "content": "测试一下你能不能听到我？"}
    ],
    "temperature": 0.7,
    "max_tokens": 256
}

resp = requests.post(url, json=payload, timeout=300)
print(resp.status_code)
print(resp.text)