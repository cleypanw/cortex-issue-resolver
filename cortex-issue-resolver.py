import requests
import secrets
import string
import hashlib
import json
import time
import gzip
import io
import argparse
from datetime import datetime, timezone
import concurrent.futures

# ==========================================
# 1. CONFIGURATION
# ==========================================
MAX_WORKERS = 50          # Number of concurrent threads
LOG_FREQUENCY = 100       # Log progress every X items

# ==========================================
# 2. AUTHENTICATION HELPER (Advanced API Key)
# ==========================================
def get_auth_headers(api_key_id, api_key):
    nonce = "".join([secrets.choice(string.ascii_letters + string.digits) for _ in range(64)])
    timestamp = int(datetime.now(timezone.utc).timestamp()) * 1000
    auth_key = "%s%s%s" % (api_key, nonce, timestamp)
    auth_key = auth_key.encode("utf-8")
    api_key_hash = hashlib.sha256(auth_key).hexdigest()

    return {
        "x-xdr-timestamp": str(timestamp),
        "x-xdr-nonce": nonce,
        "x-xdr-auth-id": str(api_key_id),
        "Authorization": api_key_hash,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

# ==========================================
# 3. XQL STEPS (Start & Download)
# ==========================================
def start_xql_query(base_url, api_key_id, api_key, xql_query):
    url = f"{base_url}/public_api/v1/xql/start_xql_query"
    headers = get_auth_headers(api_key_id, api_key)

    print(f"--- 1. Starting Query ---")
    payload = {
        "request_data": {
            "query": xql_query,
            "tenants": [],
            "timeframe": { "relativeTime": 31536000000 }  # ~1 Year
        }
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        execution_id = data.get("reply")
        print(f"✅ Query Started. Execution ID: {execution_id}")
        return execution_id
    except Exception as e:
        print(f"❌ Failed to start query: {e}")
        return None

def wait_and_get_results(base_url, api_key_id, api_key, execution_id):
    url = f"{base_url}/public_api/v1/xql/get_query_results"
    print(f"--- 2. Waiting for Results (ID: {execution_id}) ---")

    while True:
        headers = get_auth_headers(api_key_id, api_key)
        payload = {
            "request_data": {
                "query_id": execution_id,
                "pending_flag": True,
                "limit": 300000,
                "format": "json"
            }
        }
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            reply = data.get("reply", {})
            status = reply.get("status")

            if status == "PENDING":
                print("   ... Query running. Waiting 5s.")
                time.sleep(5)
                continue
            elif status == "SUCCESS":
                print("\n✅ Query Finished.")
                results_obj = reply.get("results", {})
                stream_id = results_obj.get("stream_id") or reply.get("stream_id")

                if stream_id:
                    return download_stream(base_url, api_key_id, api_key, stream_id)
                else:
                    return results_obj.get("data", [])
            else:
                print(f"❌ Query Failed with status: {status}")
                return []
        except Exception as e:
            print(f"❌ Error checking status: {e}")
            return []

def download_stream(base_url, api_key_id, api_key, stream_id):
    print(f"   [INFO] Downloading Stream {stream_id}...")
    url = f"{base_url}/public_api/v1/xql/get_query_results_stream"
    headers = get_auth_headers(api_key_id, api_key)
    headers["Accept-Encoding"] = "gzip"
    payload = {"request_data": {"stream_id": stream_id, "is_gzip_compressed": True}}

    results = []
    try:
        response = requests.post(url, headers=headers, json=payload, stream=True)
        response.raise_for_status()

        with gzip.GzipFile(fileobj=io.BytesIO(response.content)) as f:
            content = f.read().decode('utf-8')

        for line in content.strip().split('\n'):
            try:
                results.append(json.loads(line))
            except Exception:
                pass

        print(f"✅ Stream Downloaded. Parsed {len(results)} records.")
        return results
    except Exception as e:
        print(f"❌ Stream download failed: {e}")
        return []

# ==========================================
# 4. RESOLUTION WORKER (Dynamic Severity)
# ==========================================
def resolve_issue_worker(record, base_url, api_key_id, api_key):
    issue_id = (
        record.get("xdm__issue__id") or
        record.get("xdm.issue.id") or
        record.get("id") or
        record.get("issue_id")
    )

    if not issue_id:
        return False

    issue_severity = (
        record.get("xdm__issue__severity") or
        record.get("xdm.issue.severity") or
        record.get("severity") or
        "HIGH"
    )

    url = f"{base_url}/public_api/v1/issue/{issue_id}"
    headers = get_auth_headers(api_key_id, api_key)

    payload = {
        "request_data": {
            "update_data": {
                "status": "Resolved",
                "status_resolution_reason": "resolved - other",
                "status_resolution_comment": "Auto-resolved via Batch Script",
                "severity": issue_severity
            }
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload)

        if response.status_code == 429:
            time.sleep(2)
            return resolve_issue_worker(record, base_url, api_key_id, api_key)

        if response.status_code in [200, 201, 202, 204]:
            return True
        else:
            return False

    except Exception:
        return False

# ==========================================
# MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cortex XDR Issue Resolver - Mass resolve issues via XQL query")
    parser.add_argument("--api-key-id", required=True, help="API Key ID")
    parser.add_argument("--api-key", required=True, help="Advanced API Key")
    parser.add_argument("--url", required=True, help="Cortex XDR API base URL (e.g. https://api-xxx.xdr.eu.paloaltonetworks.com)")
    parser.add_argument("--xql", required=True, help="XQL query to select issues to resolve")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS, help=f"Number of concurrent threads (default: {MAX_WORKERS})")
    args = parser.parse_args()

    start_time = time.time()

    print("\n🚀 CORTEX ISSUE RESOLVER")
    print(f"   URL: {args.url}")
    print(f"   XQL: {args.xql.strip()}")

    # 1. Fetch Data
    exec_id = start_xql_query(args.url, args.api_key_id, args.api_key, args.xql)

    if exec_id:
        # 2. Download Records
        all_records = wait_and_get_results(args.url, args.api_key_id, args.api_key, exec_id)
        total_count = len(all_records)

        if total_count == 0:
            print("\nNo issues found matching the query. Exiting.")
            exit()

        # 3. Validation step
        print(f"\n⚠️  Found {total_count} issues matching the query.")
        confirm = input(f"Do you want to resolve all {total_count} issues? (yes/no): ").strip().lower()

        if confirm not in ("yes", "y"):
            print("❌ Aborted by user.")
            exit()

        print(f"\n--- 3. Starting PARALLEL Resolution of {total_count} Issues ---")
        print(f"   Using {args.workers} concurrent threads.")

        resolved_count = 0
        processed_count = 0

        # 4. Parallel Processing
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [
                executor.submit(resolve_issue_worker, record, args.url, args.api_key_id, args.api_key)
                for record in all_records
            ]

            for future in concurrent.futures.as_completed(futures):
                processed_count += 1
                if future.result():
                    resolved_count += 1

                if processed_count % LOG_FREQUENCY == 0:
                    elapsed = time.time() - start_time
                    rate = processed_count / elapsed if elapsed > 0 else 0
                    percent = (processed_count / total_count) * 100
                    remaining = (total_count - processed_count) / rate if rate > 0 else 0

                    print(f"   ... {processed_count}/{total_count} ({percent:.1f}%) | Speed: {rate:.1f}/sec | Resolved: {resolved_count} | ETA: {remaining/60:.1f} min")

        print(f"\n✅ JOB COMPLETE. Resolved {resolved_count} of {total_count} issues.")
