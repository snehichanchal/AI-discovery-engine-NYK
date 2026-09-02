import os

def query_llm(provider: str, api_key: str, model_name: str, prompt: str, system_prompt: str = "You are a helpful AI discovery engine assistant.") -> str:
    """
    Unified function to send prompts to 4 major LLM providers:
    - Gemini (Google)
    - ChatGPT (OpenAI)
    - Claude (Anthropic)
    - DeepSeek (DeepSeek AI)
    """
    if not api_key:
        return "⚠️ Error: Please enter a valid API key in the sidebar for the selected provider."

    provider = provider.lower().strip()

    try:
        if provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            target_model = model_name if model_name else "gemini-1.5-flash"
            model = genai.GenerativeModel(
                model_name=target_model,
                system_instruction=system_prompt
            )
            response = model.generate_content(prompt)
            return response.text

        elif provider in ["chatgpt", "openai"]:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            target_model = model_name if model_name else "gpt-4o-mini"
            response = client.chat.completions.create(
                model=target_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )
            return response.choices[0].message.content

        elif provider in ["claude", "anthropic"]:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            target_model = model_name if model_name else "claude-3-5-sonnet-20240620"
            response = client.messages.create(
                model=target_model,
                max_tokens=2048,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return response.content[0].text

        elif provider == "deepseek":
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
            target_model = model_name if model_name else "deepseek-chat"
            response = client.chat.completions.create(
                model=target_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )
            return response.choices[0].message.content

        else:
            return f"⚠️ Error: Unsupported provider '{provider}'. Supported providers are: Gemini, ChatGPT, Claude, DeepSeek."

    except Exception as e:
        return f"❌ API Error ({provider.capitalize()}): {str(e)}"
