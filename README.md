# MedAgent-EHR — 醫療 EHR Agentic AI

自架 LLM 的臨床 agent:在標準 **FHIR 電子病歷(EHR)** 環境中,由模型**自己規劃步驟、呼叫工具、執行查詢與寫入,並在寫入病歷前自我把關**。以史丹佛 **MedAgentBench(300 題)** 的官方評分驗證。

> **成果**:在 MedAgentBench 官方 grader 上達 **~88%(259–263 / 300)**,**高於論文公布最佳 baseline(GPT-4o 72% / Claude 3.5 Sonnet 70%)**。底層模型可在 Qwen ↔ Gemma 間切換而分數近乎持平,驗證系統與模型解耦。
>
> ⚠️ *此分數為「對齊該 benchmark 的 agent 系統」表現,非原始模型能力的純比較。*

## 這是什麼

不是「問一句答一句」的聊天式 AI,而是 **agentic AI**:LLM 驅動的 **不固定路徑、不固定步數** 控制流,搭配寫入前的安全閘。完全自架於本地 GPU,不依賴雲端 LLM API。

## 架構

```
臨床任務 → Planner(拆解計畫)
        → Executor(ReAct loop:觀察結果 → 決定下一步)⇄ MCP 工具 ⇄ FHIR
        → Verifier(寫入前安全閘:approve → commit / reject → 重試)
        → 最終答案
```

- **Planner / Executor / Verifier** 三角色皆由 LLM 驅動。
- **兩階段寫入**(stage → commit)+ Verifier 把關 + 醫療碼/劑量驗證。
- 工具透過 **MCP** 串接 **HAPI FHIR R4**,所有讀寫走標準 FHIR API。

(完整架構圖見 `docs/architecture.svg`)

## 技術堆疊

- **LLM**:自架開源模型(預設 **Gemma-4-26B-A4B-it**,亦驗證過 Qwen3.6-35B-A3B),以 **llama.cpp** 跑 GGUF
- **Agent**:Planner / Executor(ReAct)/ Verifier
- **工具與資料**:**MCP**(`fhir-mcp-server`)、**HAPI FHIR R4**
- **評測**:MedAgentBench 官方 refsol grader
- **其他**:Python、Flask(web demo)

## 專案結構

```
medagent-ehr/        # agent 核心(planner/executor/verifier、prompts、benchmark runner、web demo)
fhir-mcp-server/     # MCP 工具層(讀寫 FHIR、醫療碼解析、計算)
docs/                # 架構圖、成效圖、portfolio 說明
```

## 快速開始

```bash
# 1. 安裝(Python 3.12)
python -m venv .venv && . .venv/Scripts/activate   # Windows: .\.venv\Scripts\activate
pip install -e ".\fhir-mcp-server[dev]"
pip install -e ".\medagent-ehr[dev]"

# 2. 設定:複製範例 .env 並填入你的值(LLM endpoint、FHIR URL 等)
cp fhir-mcp-server/.env.example fhir-mcp-server/.env
cp medagent-ehr/.env.example   medagent-ehr/.env

# 3. 起服務
#   (a) llama-server 載入一個 GGUF 模型(OpenAI 相容 /v1)
#   (b) HAPI FHIR R4(Docker;跑分用 MedAgentBench 預灌資料的 image)
#   (c) python -m fhir_mcp.server      # MCP 工具層
#   (d) python -m medagent.web.app     # (選用)瀏覽器 demo
```

## MedAgentBench 資料與評分程式(需另行取得)

本 repo **不附** MedAgentBench 的測試資料與官方評分程式(版權屬原作者)。請自 [MedAgentBench](https://github.com/stanfordmlgroup/MedAgentBench) 取得:

- `test_data_v2.json` → 放到專案根目錄
- 官方 `refsol.py` / `utils.py` → 放到 `medagent-ehr/benchmark/medagentbench_official/`

（缺評分程式時,benchmark runner 仍可跑,但只會評分 task1。）

跑分:
```bash
python medagent-ehr/benchmark/run_medagentbench.py test_data_v2.json \
  --fhir-api-base http://localhost:8080/fhir/ \
  --out medagent-ehr/benchmark/results/run.json
```

## 評測結果

| | MedAgentBench Overall |
|---|---|
| 本專案(自架 Gemma-4 + 工具對齊)| **~88%(259–263/300)** |
| GPT-4o(論文)| 72% |
| Claude 3.5 Sonnet（論文)| 70% |

- 9 類任務穩定共 258/270;task10(條件 + `[值,時間]` 特殊格式)為部署模型的已知輸出弱項,以範圍誠實表述。
- 從 Qwen 遷移至 Gemma-4(法規合規)幾乎零程式改動、分數近乎持平 → 系統不綁單一模型。

## 授權

本專案自有程式碼採 [MIT License](LICENSE)。MedAgentBench 的資料與評分程式版權屬其原作者,請依其授權使用。
