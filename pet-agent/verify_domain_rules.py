#!/usr/bin/env python3
"""Section 13 evidence: domain validation rules, checked directly against petstore-api.

第 13 节证据之一:直接对着 petstore-api 检查领域校验规则,不经过 agent。

These three Section 13 scenarios are properties of petstore-api's own
Pydantic models (see app/schemas.py), not something the CLI conversation can
exercise (the CLI never creates a pet, and never sends a raw, un-validated
price range - the agent only ever calls pet-mcp's typed tools). So this
script talks to petstore-api directly with plain HTTP, the same way an
external, untrusted client would, and checks the response codes:

  - Invalid tail length (< 1 cm)      -> rejected (422)
  - Boundary tail length (exactly 1)  -> accepted (201)
  - Invalid price range (min > max)   -> rejected (422)

这三个第 13 节场景本身就是 petstore-api 自己的 Pydantic 模型的属性(见
app/schemas.py),不是 CLI 对话能测出来的东西(CLI 从来不会创建宠物,也从来
不会发一个没校验过的原始价格区间——agent 只会调用 pet-mcp 那几个有类型的工
具)。所以这个脚本直接用最普通的 HTTP 跟 petstore-api 对话,就跟一个不受信任
的外部客户端一样,然后检查返回的状态码。

Needs only the standard library - no uv/venv/LLM required. Run it either on
the host (petstore-api's port is published to localhost) or inside the stack:

    python3 verify_domain_rules.py
    # or, from the top-level directory:
    docker compose run --rm -T pet-agent python3 verify_domain_rules.py

Reads PETSTORE_API_BASE_URL from the environment (default:
http://localhost:8000 - the host-published port from the top-level
docker-compose.yml).

只需要标准库——不需要 uv/venv/LLM。既可以在宿主机上跑(petstore-api 的端口
发布到了 localhost),也可以在这套环境内部跑:

    python3 verify_domain_rules.py
    # 或者,在顶层目录下:
    docker compose run --rm -T pet-agent python3 verify_domain_rules.py

从环境变量 PETSTORE_API_BASE_URL 读取地址(默认 http://localhost:8000——顶层
docker-compose.yml 发布到宿主机的那个端口)。

This creates a small number of throwaway test pets in the real database
(tagged "verify-step11" so they are easy to spot/clean up later) - it does
not touch or purchase any of the seeded inventory.

会在真实数据库里创建少量一次性的测试宠物(打了 "verify-step11" 标签,方便以
后辨认/清理)——不会碰到或者购买种子库存里的任何一只宠物。
"""

import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("PETSTORE_API_BASE_URL", "http://localhost:8000")

# Named to avoid ruff/bandit's S105 ("possible hardcoded password") false
# positive, which triggers on any top-level string constant whose NAME
# resembles "PASS" - these are pass/fail labels, not credentials.
# 起这个名字是为了避开 ruff/bandit 的 S105("疑似硬编码密码")误报——它是按
# 变量*名字*像不像 "PASS" 来触发的,这里其实是通过/失败的标签,不是凭据。
RESULT_LABELS = {True: "PASS", False: "FAIL"}
results: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str) -> None:
    status = RESULT_LABELS[ok]
    results.append((name, status, detail))
    print(f"[{status}] {name}: {detail}")


def http(method: str, path: str, body: dict[str, object] | None = None) -> tuple[int, dict[str, object]]:
    url = BASE_URL + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    # S310 (audit URL open for permitted schemes) is a false positive here:
    # `url` is always BASE_URL (a local config value, http(s) only) plus a
    # fixed literal path - never attacker/user-controlled input.
    # S310(审计 URL scheme)在这里是误报:`url` 永远是 BASE_URL(一个本地配置
    # 值,只会是 http(s))加上一段写死的路径——不是攻击者/用户能控制的输入。
    req = urllib.request.Request(url, data=data, method=method, headers=headers)  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, (json.loads(raw) if raw else {})


def base_pet(**overrides: object) -> dict[str, object]:
    pet = {
        "name": "Verify Test Pet",
        "species": "rabbit",
        "breed": "Test",
        "age_months": 12,
        "weight_kg": 2.0,
        "tail_length_cm": 5.0,
        "description": "A pet created only for Section 13 automated verification.",
        "price_eur": 10.0,
        "availability": "available",
        "tags": ["verify-step11"],
        "photo_references": ["verify.jpg"],
    }
    pet.update(overrides)
    return pet


def main() -> int:
    print(f"Petstore API: {BASE_URL}")
    print("=" * 70)

    status, _ = http("GET", "/health")
    if status != 200:
        print(f"error: petstore-api is not reachable/healthy at {BASE_URL} (status={status})", file=sys.stderr)
        print("Start it first: docker compose up -d db petstore-api", file=sys.stderr)
        return 2

    # Section 13: "Invalid tail length" - a pet with a tail shorter than 1 cm is rejected.
    status, body = http("POST", "/pets", base_pet(tail_length_cm=0.5))
    record("Invalid tail length rejected", status == 422, f"status={status} (want 422) body={body}")

    # Section 13: "Boundary tail length" - exactly 1 cm is accepted.
    status, body = http("POST", "/pets", base_pet(tail_length_cm=1.0))
    record("Boundary tail length (1cm) accepted", status == 201, f"status={status} (want 201) id={body.get('id')}")

    # Section 13: "Invalid price range" - a minimum price above the maximum price is rejected.
    status, body = http("GET", "/pets?min_price_eur=500&max_price_eur=100")
    record("Invalid price range (min > max) rejected", status == 422, f"status={status} (want 422) body={body}")

    # Sanity check in the other direction, so a PASS above isn't just "everything 422s".
    status, body = http("GET", "/pets?min_price_eur=100&max_price_eur=500")
    record("Valid price range (min <= max) accepted", status == 200, f"status={status} (want 200)")

    print("=" * 70)
    failed = [name for name, status, _ in results if status == RESULT_LABELS[False]]
    if failed:
        print(f"{len(failed)} check(s) FAILED: {', '.join(failed)}")
        return 1
    print(f"All {len(results)} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
