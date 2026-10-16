import os
import time
from pathlib import Path
import requests
from requests.auth import HTTPBasicAuth
import config

_sim_ticket_counter = 100

class JiraService:
    def _get_config(self):
        """Dynamically reload and return the latest Jira settings from .env and config."""
        try:
            from dotenv import load_dotenv
            load_dotenv(config.ENV_FILE, override=True)
        except Exception:
            pass

        url = (os.environ.get("JIRA_URL") or getattr(config, "JIRA_URL", "") or "").strip().rstrip("/")
        email = (os.environ.get("JIRA_EMAIL") or getattr(config, "JIRA_EMAIL", "") or "").strip()
        token = (os.environ.get("JIRA_API_TOKEN") or getattr(config, "JIRA_API_TOKEN", "") or "").strip()
        project = (os.environ.get("JIRA_PROJECT_KEY") or getattr(config, "JIRA_PROJECT_KEY", "BANK") or "BANK").strip()
        
        sim_val = os.environ.get("JIRA_SIMULATION_MODE")
        if sim_val is not None:
            sim_mode = sim_val.lower() in ("true", "1", "yes")
        else:
            sim_mode = getattr(config, "JIRA_SIMULATION_MODE", False)

        return url, email, token, project, sim_mode

    def is_configured(self) -> bool:
        url, email, token, project, _ = self._get_config()
        if not (url and email and token and project):
            return False
        if "your-domain" in url or "your-jira-api-token" in token or "your-email" in email:
            return False
        return True

    def test_connection(self):
        url, email, token, project, sim_mode = self._get_config()

        if not all([url, email, token, project]):
            if sim_mode:
                return {
                    "success": True,
                    "message": f"Simulation Mode Active: Ready to generate tickets under project '{project}'."
                }
            return {
                "success": False,
                "message": "Jira credentials incomplete. Set JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN, and JIRA_PROJECT_KEY in settings or .env."
            }
        try:
            res = requests.get(
                f"{url}/rest/api/3/myself",
                auth=HTTPBasicAuth(email, token),
                headers={"Accept": "application/json"},
                timeout=12
            )
            if res.status_code == 401:
                if sim_mode:
                    return {
                        "success": True,
                        "message": f"Simulation Mode Active (Cloud Auth HTTP 401). Demo project '{project}' ready."
                    }
                return {
                    "success": False,
                    "message": "Jira Authentication Failed (HTTP 401). Invalid Jira email or API Token."
                }
            elif res.status_code != 200:
                if sim_mode:
                    return {
                        "success": True,
                        "message": f"Simulation Mode Active (Cloud HTTP {res.status_code}). Demo project '{project}' ready."
                    }
                return {
                    "success": False,
                    "message": f"Jira Auth Returned HTTP {res.status_code}: {res.text[:150]}"
                }
            user_data = res.json()
            user_name = user_data.get("displayName", email)

            res_proj = requests.get(
                f"{url}/rest/api/3/project/{project}",
                auth=HTTPBasicAuth(email, token),
                headers={"Accept": "application/json"},
                timeout=12
            )
            if res_proj.status_code in (403, 404):
                if sim_mode:
                    return {
                        "success": True,
                        "message": f"Connected as {user_name}! Simulation Mode active for target project '{project}'."
                    }
                return {
                    "success": False,
                    "message": f"Authenticated as {user_name}, but project '{project}' was not found or access denied."
                }

            proj_data = res_proj.json()
            return {
                "success": True,
                "message": f"Connected as {user_name}! Target Project: {proj_data.get('name', project)} ({project})"
            }
        except Exception as exc:
            if sim_mode:
                return {
                    "success": True,
                    "message": f"Simulation Mode Active. Demo project '{project}' ready."
                }
            return {"success": False, "message": f"Jira connection error: {exc}"}

    def create_ticket(self, summary, description, priority="High"):
        global _sim_ticket_counter
        url, email, token, project, sim_mode = self._get_config()

        # Map priority to Jira-supported levels
        p_map = {
            "P1": "Highest",
            "P2": "High",
            "P3": "Medium",
            "High": "High",
            "Medium": "Medium",
            "Low": "Low",
            "Critical": "Highest"
        }
        jira_priority = p_map.get(priority, "High")

        # Attempt live API call if credentials present
        if all([url, email, token, project]) and not sim_mode:
            endpoint = f"{url}/rest/api/3/issue"
            payload = {
                "fields": {
                    "project": {"key": project},
                    "summary": str(summary)[:255],
                    "description": {
                        "type": "doc",
                        "version": 1,
                        "content": [{
                            "type": "paragraph",
                            "content": [{"text": str(description)[:4000], "type": "text"}]
                        }]
                    },
                    "issuetype": {"name": "Task"},
                    "priority": {"name": jira_priority}
                }
            }
            try:
                response = requests.post(
                    endpoint,
                    json=payload,
                    auth=HTTPBasicAuth(email, token),
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json"
                    },
                    timeout=15
                )
                if response.status_code in (200, 201):
                    data = response.json()
                    ticket_key = data.get("key")
                    ticket_url = f"{url}/browse/{ticket_key}" if ticket_key else None
                    print(f"[JIRA SYNC SUCCESS] Created Jira ticket {ticket_key}: {ticket_url}")
                    return {
                        "success": True,
                        "ticket_id": ticket_key,
                        "ticket_url": ticket_url,
                        "message": f"Jira support ticket {ticket_key} created successfully in project {project}"
                    }
                else:
                    print(f"[JIRA SYNC ERROR] HTTP {response.status_code}: {response.text}")
                    # Try once more without priority in case project doesn't allow custom priority
                    payload["fields"].pop("priority", None)
                    retry_res = requests.post(
                        endpoint,
                        json=payload,
                        auth=HTTPBasicAuth(email, token),
                        headers={"Accept": "application/json", "Content-Type": "application/json"},
                        timeout=15
                    )
                    if retry_res.status_code in (200, 201):
                        data = retry_res.json()
                        ticket_key = data.get("key")
                        ticket_url = f"{url}/browse/{ticket_key}" if ticket_key else None
                        print(f"[JIRA SYNC RETRY SUCCESS] Created Jira ticket {ticket_key}: {ticket_url}")
                        return {
                            "success": True,
                            "ticket_id": ticket_key,
                            "ticket_url": ticket_url,
                            "message": f"Jira support ticket {ticket_key} created successfully in project {project}"
                        }
                    else:
                        print(f"[JIRA SYNC RETRY ERROR] HTTP {retry_res.status_code}: {retry_res.text}")
                        return {
                            "success": False,
                            "message": f"Jira creation failed (HTTP {response.status_code}): {response.text[:200]}"
                        }
            except Exception as err:
                print(f"[JIRA EXCEPTION] {err}")
                return {
                    "success": False,
                    "message": f"Jira request error: {err}"
                }

        # Fallback to simulation mode only if explicitly enabled
        if sim_mode:
            _sim_ticket_counter += 1
            ticket_key = f"{project}-{_sim_ticket_counter}"
            ticket_url = f"{url}/browse/{ticket_key}" if url else f"https://atlassian.net/browse/{ticket_key}"
            return {
                "success": True,
                "simulated": True,
                "ticket_id": ticket_key,
                "ticket_url": ticket_url,
                "message": f"Jira ticket {ticket_key} generated in Simulation Mode"
            }

        return {
            "success": False,
            "message": "Jira is not configured. Set credentials in .env with JIRA_SIMULATION_MODE=false."
        }
