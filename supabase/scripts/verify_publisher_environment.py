"""Read-only fail-closed check of GitHub publisher protection. No secret output."""

import os

import httpx

REPO = "Daddy-JJ/BackendSahamTeknikal"
ENVIRONMENT = "production-publisher"


def verify(data, policies):
    if (data.get("name") != ENVIRONMENT
            or not any(rule.get("type") == "required_reviewers" and rule.get("reviewers")
                       for rule in data.get("protection_rules", []))
            or data.get("deployment_branch_policy") != {
                "protected_branches": False, "custom_branch_policies": True}
            or [(p.get("name"), p.get("type")) for p in policies] != [("main", "branch")]):
        raise ValueError("publisher_environment_protection_not_verified")


def main():
    try:
        if (os.environ.get("GITHUB_REPOSITORY") != REPO
                or os.environ.get("GITHUB_REF") != "refs/heads/main"):
            raise ValueError("publisher_main_repository_required")
        token = os.environ.get("GH_TOKEN")
        if not token:
            raise ValueError("publisher_environment_read_access_missing")
        with httpx.Client(base_url=f"https://api.github.com/repos/{REPO}/", timeout=30,
                          headers={"Authorization": "Bearer " + token,
                                   "Accept": "application/vnd.github+json",
                                   "X-GitHub-Api-Version": "2026-03-10"}) as client:
            env = client.get("environments/" + ENVIRONMENT)
            policies = client.get("environments/" + ENVIRONMENT + "/deployment-branch-policies")
            env.raise_for_status()
            policies.raise_for_status()
            policy_data = policies.json()
            if policy_data.get("total_count") != 1:
                raise ValueError("publisher_environment_protection_not_verified")
            verify(env.json(), policy_data["branch_policies"])
        print('{"publisher_environment_protection_verified":true,"method":"GET only"}')
        return 0
    except Exception:
        print('{"publisher_environment_protection_verified":false,"production_write":false}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
