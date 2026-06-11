"""
测试API连接
"""
import requests

def test_connection():
    """测试网络连接"""
    
    print("=" * 80)
    print("测试API连接")
    print("=" * 80)
    
    # 1. 测试基本网络
    print("\n1. 测试基本网络连接...")
    try:
        response = requests.get("https://www.baidu.com", timeout=5)
        print(f"   ✓ 基本网络正常 (状态码: {response.status_code})")
    except Exception as e:
        print(f"   ❌ 基本网络失败: {e}")
        return
    
    # 2. 测试DeepSeek API
    print("\n2. 测试DeepSeek API连接...")
    api_key = "sk-ecd91655d033446b9ae8ea390e65d923"
    base_url = "https://api.deepseek.com"
    
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # 简单的测试请求
        data = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "user", "content": "hello"}
            ],
            "max_tokens": 10
        }
        
        response = requests.post(
            f"{base_url}/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"   ✓ DeepSeek API连接成功!")
            print(f"   响应: {result.get('choices', [{}])[0].get('message', {}).get('content', '')}")
        else:
            print(f"   ❌ DeepSeek API返回错误: {response.status_code}")
            print(f"   响应: {response.text}")
            
    except requests.exceptions.ConnectionError as e:
        print(f"   ❌ 连接失败 (网络错误): {e}")
        print(f"\n   💡 可能的原因:")
        print(f"      - 需要配置代理")
        print(f"      - 防火墙阻止")
        print(f"      - API endpoint不可达")
        print(f"\n   💡 建议:")
        print(f"      1. 检查是否需要设置HTTP_PROXY/HTTPS_PROXY环境变量")
        print(f"      2. 或使用本地LLM (Ollama)")
        print(f"      3. 或继续使用Mock LLM完成演示")
    except Exception as e:
        print(f"   ❌ 请求失败: {e}")
    
    # 3. 建议
    print("\n" + "=" * 80)
    print("建议方案")
    print("=" * 80)
    print("\n如果DeepSeek API无法连接,可以:")
    print("  方案1: 配置代理")
    print("    export HTTP_PROXY=http://your-proxy:port")
    print("    export HTTPS_PROXY=http://your-proxy:port")
    print()
    print("  方案2: 使用Ollama (本地LLM)")
    print("    - 安装Ollama")
    print("    - 启动模型: ollama run llama2")
    print("    - 修改run_production.py使用OllamaClient")
    print()
    print("  方案3: 使用Mock LLM (用于测试)")
    print("    - 已有test_complete_demo.py演示完整流程")
    print("    - 可以验证所有功能")


if __name__ == "__main__":
    test_connection()
