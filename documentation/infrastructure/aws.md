# AWS account

Mitchell Wasson confirmed that the capstone AWS account has been provisioned and two designated teammates have admin access (Grazia and Ernesto).

## Access

- Admins sign in from a Cisco laptop via the [AWS console portal](https://go2.cisco.com/aws) and select the admin role.
- The admins arrange appropriately permissioned access for other team members. Team access arrangements are still open.

## Account restrictions

- Use the account only for AgentWatch and handle public data only. Keep Cisco data out of the account.
- Cisco monitors the account for security violations. The team must address any guardrail violations.
- Keep S3 buckets private and network interfaces inaccessible to the general public. Restrict instance access to approved IP addresses. Crypto mining is prohibited.
- The budget is USD $1,000 through the end of January 2027 and resets to USD $1,000 for February through April 2027. Additional funding is not guaranteed.
- Automatic account deletion is expected around mid-May 2027. Confirm the exact date with Mitchell.

## Mitchell’s recommendations

- Use one agreed AWS region for project resources.
- Manage resources with Terraform or AWS CloudFormation.
- Designate an AWS lead, ideally one of the two admins.
- Use Bedrock for AgentWatch prototypes where useful. Mitchell recommends against using it for personal coding assistants because of cost.

## Open decisions

- AWS region
- AWS lead
- Team access arrangements
- Exact automatic deletion date
