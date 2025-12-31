import time
from openai import OpenAI

# 你的本地端口已经被转发到服务器 8000
client = OpenAI(
    base_url="http://127.0.0.1:8001/v1",
    api_key="not-needed"
)

def test_once(question):
    t1 = time.time()
    try:
        resp = client.chat.completions.create(
            model="Qwen2.5-72B",
            messages=[{"role": "user", "content": question}],
            max_tokens=80,
        )
        t2 = time.time()

        answer = resp.choices[0].message.content
        print(f"✔ Success ({t2 - t1:.2f}s): {answer[:80]}...")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    print("🚀 Testing vLLM API connectivity...")

    QUESTIONS = [
        "What is the capital of Japan?",
        "Explain quantum computing in one sentence.",
        "写一句哲学句子。",
        "Difference between RAM and VRAM?",
        "Why do large models need tensor parallelism?",
    ]

    for i, q in enumerate(QUESTIONS, 1):
        print(f"\n[{i}/{len(QUESTIONS)}] Asking: {q}")
        test_once(q)