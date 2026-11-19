import os
import requests
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("STARTGG_TOKEN")

url="https://api.start.gg/gql/alpha"
headers = {"Authorization": f"Bearer {token}"}
query = """query {
  currentUser {
    id
    player { gamerTag }
  }
}"""