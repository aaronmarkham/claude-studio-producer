"""Quick test to verify everything is working"""
import asyncio
from dotenv import load_dotenv
from core.secrets import get_api_key

async def main():
    load_dotenv()

    print("Testing Claude Agent SDK Setup...")
    print()

    api_key = get_api_key("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your_key_here":
        print("[ERROR] API key not set (check keychain or env)")
        print()
        print("Steps to fix:")
        print("1. Get API key: https://console.anthropic.com/")
        print("2. Run: claude-studio secrets set ANTHROPIC")
        print("   (or set ANTHROPIC_API_KEY env var)")
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
