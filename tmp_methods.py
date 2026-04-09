import os
import sys
from dotenv import load_dotenv

workspace = r"c:/Users/adityakota/NiftyOptionsTrading"
load_dotenv(os.path.join(workspace, ".env"))
sys.path.append(workspace)

import breeze_connect
breeze = breeze_connect.BreezeConnect(api_key=os.getenv("API_KEY"))
print("BreezeConnect methods:")
for method in dir(breeze):
    if not method.startswith("_"):
        print(method)
