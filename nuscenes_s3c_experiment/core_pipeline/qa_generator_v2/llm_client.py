"""
LLM客户端适配器
支持多种LLM接口: OpenAI, Claude, 本地模型等
"""
from typing import Dict, Optional, List
from abc import ABC, abstractmethod


class BaseLLMClient(ABC):
    """LLM客户端基类"""
    
    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """
        生成文本
        
        Args:
            prompt: 输入prompt
            **kwargs: 额外参数（如temperature, max_tokens等）
        
        Returns:
            生成的文本
        """
        pass


class OpenAIClient(BaseLLMClient):
    """OpenAI API客户端"""
    
    def __init__(self, api_key: str, model: str = "gpt-4", base_url: str = None, verify_ssl: bool = True, **default_params):
        """
        Args:
            api_key: OpenAI API key
            model: 模型名称 (gpt-4, gpt-3.5-turbo, deepseek-chat等)
            base_url: API base URL (用于DeepSeek等兼容API)
            verify_ssl: 是否验证SSL证书
            **default_params: 默认参数（temperature, max_tokens等）
        """
        try:
            import openai
            import httpx
            self.openai = openai
            
            # 创建http_client
            http_client = None if verify_ssl else httpx.Client(verify=False)
            
            if base_url:
                self.client = openai.OpenAI(api_key=api_key, base_url=base_url, http_client=http_client)
            else:
                self.client = openai.OpenAI(api_key=api_key, http_client=http_client)
        except ImportError as e:
            raise ImportError(f"请安装所需库: pip install openai httpx - {e}")
        
        self.model = model
        self.default_params = {
            "temperature": 0.7,
            "max_tokens": 2048,  # 与VQA pipeline保持一致
            **default_params
        }
    
    def generate(self, prompt: str, **kwargs) -> str:
        """生成文本"""
        params = {**self.default_params, **kwargs}
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant for autonomous driving scene QA."},
                    {"role": "user", "content": prompt}
                ],
                temperature=params["temperature"],
                max_tokens=params["max_tokens"],
                stream=False  # 与VQA pipeline一致
            )
            # 检查finish_reason
            if response.choices[0].finish_reason == "length":
                print(f"警告: LLM响应被截断 (max_tokens={params['max_tokens']})")
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"OpenAI API调用失败: {e}")
            raise


class ClaudeClient(BaseLLMClient):
    """Anthropic Claude API客户端"""
    
    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022", **default_params):
        """
        Args:
            api_key: Anthropic API key
            model: 模型名称
            **default_params: 默认参数
        """
        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key)
        except ImportError:
            raise ImportError("请安装anthropic库: pip install anthropic")
        
        self.model = model
        self.default_params = {
            "temperature": 0.7,
            "max_tokens": 500,
            **default_params
        }
    
    def generate(self, prompt: str, **kwargs) -> str:
        """生成文本"""
        params = {**self.default_params, **kwargs}
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=params["max_tokens"],
                temperature=params["temperature"],
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return response.content[0].text.strip()
        except Exception as e:
            print(f"Claude API调用失败: {e}")
            raise


class LocalLLMClient(BaseLLMClient):
    """本地LLM客户端（通过HTTP API）"""
    
    def __init__(self, api_url: str, model: str = None, **default_params):
        """
        Args:
            api_url: 本地LLM API地址（如Ollama, vLLM等）
            model: 模型名称
            **default_params: 默认参数
        """
        try:
            import requests
            self.requests = requests
        except ImportError:
            raise ImportError("请安装requests库: pip install requests")
        
        self.api_url = api_url
        self.model = model
        self.default_params = {
            "temperature": 0.7,
            "max_tokens": 500,
            **default_params
        }
    
    def generate(self, prompt: str, **kwargs) -> str:
        """生成文本"""
        params = {**self.default_params, **kwargs}
        
        # 适配不同的本地API格式
        payload = {
            "prompt": prompt,
            "temperature": params["temperature"],
            "max_tokens": params["max_tokens"]
        }
        
        if self.model:
            payload["model"] = self.model
        
        try:
            response = self.requests.post(self.api_url, json=payload)
            response.raise_for_status()
            result = response.json()
            
            # 尝试不同的响应格式
            if "text" in result:
                return result["text"].strip()
            elif "response" in result:
                return result["response"].strip()
            elif "content" in result:
                return result["content"].strip()
            else:
                raise ValueError(f"无法解析响应格式: {result.keys()}")
        except Exception as e:
            print(f"本地LLM API调用失败: {e}")
            raise


class OllamaClient(BaseLLMClient):
    """Ollama本地LLM客户端"""
    
    def __init__(self, model: str = "llama3", host: str = "http://localhost:11434", **default_params):
        """
        Args:
            model: Ollama模型名称
            host: Ollama服务地址
            **default_params: 默认参数
        """
        try:
            import requests
            self.requests = requests
        except ImportError:
            raise ImportError("请安装requests库: pip install requests")
        
        self.model = model
        self.api_url = f"{host}/api/generate"
        self.default_params = {
            "temperature": 0.7,
            **default_params
        }
    
    def generate(self, prompt: str, **kwargs) -> str:
        """生成文本"""
        params = {**self.default_params, **kwargs}
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": params["temperature"]
            }
        }
        
        try:
            response = self.requests.post(self.api_url, json=payload)
            response.raise_for_status()
            result = response.json()
            return result["response"].strip()
        except Exception as e:
            print(f"Ollama API调用失败: {e}")
            raise


class AzureOpenAIClient(BaseLLMClient):
    """Azure OpenAI客户端"""
    
    def __init__(self, api_key: str, endpoint: str, deployment_name: str, api_version: str = "2024-02-15-preview", **default_params):
        """
        Args:
            api_key: Azure API key
            endpoint: Azure endpoint
            deployment_name: 部署名称
            api_version: API版本
            **default_params: 默认参数
        """
        try:
            import openai
            self.openai = openai
            self.client = openai.AzureOpenAI(
                api_key=api_key,
                azure_endpoint=endpoint,
                api_version=api_version
            )
        except ImportError:
            raise ImportError("请安装openai库: pip install openai")
        
        self.deployment_name = deployment_name
        self.default_params = {
            "temperature": 0.7,
            "max_tokens": 500,
            **default_params
        }
    
    def generate(self, prompt: str, **kwargs) -> str:
        """生成文本"""
        params = {**self.default_params, **kwargs}
        
        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant for autonomous driving scene QA."},
                    {"role": "user", "content": prompt}
                ],
                temperature=params["temperature"],
                max_tokens=params["max_tokens"]
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Azure OpenAI API调用失败: {e}")
            raise


# 使用示例和测试
if __name__ == "__main__":
    print("LLM Client 使用示例\n")
    
    print("=" * 60)
    print("1. OpenAI GPT-4")
    print("=" * 60)
    print("""
from llm_client import OpenAIClient

client = OpenAIClient(
    api_key="your-api-key",
    model="gpt-4",
    temperature=0.7
)

response = client.generate("What is autonomous driving?")
print(response)
""")
    
    print("\n" + "=" * 60)
    print("2. Anthropic Claude")
    print("=" * 60)
    print("""
from llm_client import ClaudeClient

client = ClaudeClient(
    api_key="your-api-key",
    model="claude-3-5-sonnet-20241022"
)

response = client.generate("Explain scene graphs.")
print(response)
""")
    
    print("\n" + "=" * 60)
    print("3. Ollama (本地)")
    print("=" * 60)
    print("""
from llm_client import OllamaClient

client = OllamaClient(
    model="llama3",
    host="http://localhost:11434"
)

response = client.generate("Generate a question about cars.")
print(response)
""")
    
    print("\n" + "=" * 60)
    print("4. 使用LLM生成QA")
    print("=" * 60)
    print("""
from llm_qa_generator import LLMQAGenerator
from llm_client import OpenAIClient

# 创建LLM客户端
llm_client = OpenAIClient(api_key="your-api-key")

# 创建QA生成器
generator = LLMQAGenerator(llm_client=llm_client)

# 加载场景图
with open("scene_graph.json", 'r') as f:
    scene_data = json.load(f)

# 生成问答对
qa_pairs = generator.generate(
    scene_data,
    difficulties=["L0", "L1"],
    num_questions_per_template=2
)

# 保存结果
generator.save_qa_pairs(qa_pairs, "qa_output.json")
""")
