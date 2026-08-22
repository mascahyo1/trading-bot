import os
from dotenv import load_dotenv

print(f"CWD before: {os.getcwd()}")
script_dir = os.path.dirname(os.path.abspath(__file__))
print(f"Script dir: {script_dir}")
os.chdir(script_dir)
print(f"CWD after: {os.getcwd()}")
print(f".env exists: {os.path.exists('.env')}")
print(f".env full path: {os.path.abspath('.env')}")

# Try load_dotenv with explicit path
result = load_dotenv(".env")
print(f"load_dotenv result: {result}")

print(f"INDODAX_API_KEY: {os.getenv('indodax_API_KEY', 'NOT SET')}")
print(f"indodax_api_key: {os.getenv('indodax_api_key', 'NOT SET')}")
