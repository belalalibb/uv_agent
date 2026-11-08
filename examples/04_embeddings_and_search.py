"""Example 04: Vector Embeddings and Document Reranking."""

import asyncio
import sys
from pathlib import Path

# Add external_platform_client to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from client import GatewayClient, GatewayConfig, SmartRouter


async def main() -> None:
    config = GatewayConfig(
        base_url="http://127.0.0.1:8800",
        gateway_secret="live-demo-secret-key-bolla-zizo",
        secret_version=1,
    )
    router = SmartRouter({
        "voyage": "rtk_voyage_production",
        "upstage": "rtk_upstage_production",
    })

    async with GatewayClient(config=config, router=router) as client:
        # A. Vector Embeddings
        print("Generating Vector Embeddings (Voyage AI)...")
        sentences = [
            "الذكاء الاصطناعي يغير شكل البرمجة الحديثة.",
            "قواعد البيانات الموزعة تتطلب عناية خاصة بالتزامن.",
        ]

        try:
            emb_res = await client.create_embeddings(
                route_token="voyage",
                model="voyage-3-large",
                inputs=sentences,
            )
            print(f"Generated {len(emb_res.output.embeddings)} vectors.")
            print(f"Vector Dimensions: {emb_res.output.dimensions}")
        except Exception as e:
            print(f"Embeddings call failed (expected if mock/live credentials not configured): {e}")

        # B. Document Reranking
        print("\nReranking candidate documents...")
        query = "أفضل لغات البرمجة لتطبيقات الذكاء الاصطناعي"
        documents = [
            "لغة بايثون هي الأكثر شيوعاً في الذكاء الاصطناعي وعلوم البيانات.",
            "لغة C++ توفر أداءً فائقاً وتستخدم في بناء المحركات الأساسية.",
            "الطهي فن يتطلب مكونات طازجة ووصفات دقيقة.",
        ]

        try:
            rerank_res = await client.rerank_documents(
                route_token="voyage",
                model="rerank-2",
                query=query,
                documents=documents,
                top_n=2,
            )
            print(f"Reranking completed in {rerank_res.latency_ms} ms.")
            for item in rerank_res.output.results:
                print(f"Document #{item.index}: Score={item.relevance_score:.4f} -> {documents[item.index]}")
        except Exception as e:
            print(f"Rerank call failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())

