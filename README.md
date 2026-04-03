# 🛡️ Cortex Issue Resolver

![Python](https://img.shields.io/badge/Python-3.8%2B-blue?style=for-the-badge&logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Cortex%20XDR%20%7C%20XQL-orange?style=for-the-badge)

**Automated Bulk Remediation Tool for Cortex XDR/Cloud**

This script leverages the **XQL Stream API** and **Multi-Threading** to resolve security issues. It is designed for high-volume environments (e.g., 10k+ issues).

---
## 🔑 API Requirements

To successfully execute XQL queries, you must generate your API Key with the following settings:

| Paramètre | Valeur Requise |
| :--- | :---: |
| **Security Level** | `Advanced` | 
| **Role** | `Instance Admin` | 

> [!NOTE]
> Keys with lower roles will fail to execute XQL APIs.

## How to Use

### 1. Prepare your Query
Before running the script, ensure you have a valid XQL query ready that filters only the issues you want to resolve.

**Example query:**
```
dataset = issues 
| filter xdm.issue.detection.method = "CAS_SECRET_SCANNER" and xdm.issue.name = "AWS Access Key detected in code" and xdm.issue.status.progress in (IN_PROGRESS, NEW)
```

### 2. Run

```bash
python cortex-issue-resolver.py \
  --api-key-id "YOUR_API_KEY_ID" \
  --api-key "YOUR_API_KEY" \
  --url "https://api-xxx.xdr.eu.paloaltonetworks.com" \
  --xql 'dataset = issues | filter xdm.issue.status.progress in (IN_PROGRESS, NEW)'
```

### Arguments

| Argument | Required | Description |
| :--- | :---: | :--- |
| `--api-key-id` | Yes | API Key ID |
| `--api-key` | Yes | Advanced API Key |
| `--url` | Yes | Cortex XDR API base URL (e.g. `https://api-xxx.xdr.eu.paloaltonetworks.com`) |
| `--xql` | Yes | XQL query to select issues to resolve |
| `--workers` | No | Number of concurrent threads (default: `50`) |

The script will display the number of matching issues and **ask for confirmation** before proceeding with the resolution.

## Performance Settings

* `--workers`: Runs N resolution requests in parallel (default: `50`). It is recommended to keep this value as is.
* Progress is logged to the console every 100 items processed.

> [!WARNING]
> This script performs bulk resolution on production data. Always verify your XQL query results in the Cortex Console first to ensure you are targeting the correct issues.
