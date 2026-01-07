"""Quick test to verify everything is working"""
import asyncio
import os
from dotenv import load_dotenv

async def main():
    load_dotenv()
    
    print("Testing Claude Agent SDK Setup...")
    print()
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your_key_here":
        print("[ERROR] API key not set in .env file")
        print()
        print("Steps to fix:")
        print("1. Get API key: https://console.anthropic.com/")
        print("2. Edit .env file")
        print("3. Replace 'your_key_here' with your key")
        return
    
    print("[OK] API key found")
    
    try:
        from claude_agent_sdk import query
        print("[OK] Claude Agent SDK imported")
    except ImportError as e:
        print(f"[ERROR] {e}")
        return
    
    print()
    print("Testing API connection...")
    try:
        async for message in query(prompt="Say 'Hello! Setup successful!'"):
            print(f"   Claude: {message}")
        print()
        print("SUCCESS! Ready to build!")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__ == "__main__":
    asyncio.run(main())
