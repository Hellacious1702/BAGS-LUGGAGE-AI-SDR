import os

from dotenv import load_dotenv
from firecrawl import Firecrawl
from openai import OpenAI

load_dotenv()

fc_key = os.getenv("FIRECRAWL_API_KEY")
nv_key = os.getenv("NVIDIA_NIM_API_KEY")
print("Firecrawl key loaded:", bool(fc_key))
print("NVIDIA key loaded:   ", bool(nv_key))

fc = Firecrawl(api_key=fc_key)
print("\nFirecrawl credit usage:", fc.get_credit_usage())

nv = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=nv_key)
nemotron = [m.id for m in nv.models.list() if "nemotron" in m.id.lower()]
print("\nNemotron models available:")
for model_id in sorted(nemotron):
    print("  ", model_id)
