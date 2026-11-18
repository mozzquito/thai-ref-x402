# Thai Reference API — x402 MCP wrapper 🇹🇭

MCP server exposing **Thailand reference data** for AI agents, paid per call via [x402](https://x402.org) (HTTP 402 + USDC on Base). No API key, no signup — your wallet pays per request.

- API docs: https://api.thaical.xyz/docs
- Price: **$0.005 / call** (5000 USDC atomic units), `exact` scheme, `eip155:84532` (Base Sepolia testnet)

## Tools
| Tool | What it does |
|---|---|
| `thai_fx` | THB reference FX rates (USD/EUR/JPY/GBP/CNY → THB, ECB daily) |
| `thai_gold` | Thai gold price per baht-weight (XAU spot-derived, 96.5% estimate) |
| `thai_is_business_day` | Is a date a Thai business day? (holidays incl. substitution days) |
| `thai_add_business_days` | Add N Thai business days |

## Setup
```json
{
  "mcpServers": {
    "thai-ref": {
      "command": "python3",
      "args": ["/path/to/thai_ref_mcp.py"],
      "env": {
        "PAYMENT_PRIVATE_KEY": "0x...", 
        "THAI_REF_URL": "https://api.thaical.xyz"
      }
    }
  }
}
```
`PAYMENT_PRIVATE_KEY` = a wallet holding USDC on Base. Payments use EIP-3009 signatures — **the payer pays no gas**.

## Requirements
```bash
pip install "x402[evm]" eth-account httpx jsonschema
```

## How payment works
1. Tool call hits the API → `HTTP 402` + `PAYMENT-REQUIRED` header (the terms)
2. Client signs an EIP-3009 authorization, retries with `PAYMENT-SIGNATURE`
3. Coinbase CDP facilitator verifies & settles → `HTTP 200` + data

One request round-trip. No accounts anywhere.

## License
MIT
