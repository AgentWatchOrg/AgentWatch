# AWS account

Mitchell Wasson confirmed that the capstone AWS account has been provisioned and two designated teammates have admin access (Grazia and Ernesto).

## Access

- Admins sign in from a Cisco laptop via the [AWS console portal](https://go2.cisco.com/aws) and select the admin role.
- The designated admins will coordinate AWS access and permissions for the rest of the team.

## Account restrictions

> - The account is rated for public data only. That is, nothing from Cisco should enter this AWS account. This matches with non-Cisco employees (your teammates) getting access to the account via access keys
> - There is corporate security monitoring on the account. If you do something that trips the guardrails, you'll have to fix it. I tried to set it up so we'll get a webex message in this space if it happens.
> - The budget for the account is set at 1000USD per quarter. This means you've got 1k from now until the end of january. Then it will reset and you get 1k for Feb-April. If you use this budget then you're out of luck.
> - If you predict that you need for budget for something or run out of budget let me know and I can try to get more but really don't count on it.
> - Using the AWS account for anything other than this project (e.g. other projects, side hustles, crypto mining) is not allowed and the account will be shut down if this is the case.

Automatic account deletion is expected in May 2027.

### Security guardrails

> Known things that will trip security guardrails:
>
> - public S3 buckets
> - world-accessible network interfaces (so if you are going to make a VM, your security group needs to specify ip addresses that you will access it from and block everything else)
> - crypto mining

## Mitchell’s recommendations

> I recommend not using the Bedrock API for the purposes of powering your personal coding agents to implement the project. That will pretty quickly eat through the budget, especially with 6 of you. However, feel free to use the Bedrock API to power the claude agent in prototypes of your software system if you think there is a benefit.
>
> Another best practice would be for your team to align on a single geographic region to use. Things are a real pain if stuff gets spread across different regions and you forget where to look for something
>
> Also, I recommend using something like terraform or AWS cloud formation for resource creation and management. It allows for quick creation and teardown while keeping stuff version controlled. These days the coding agents can also create that infrastructure as code more quickly than you can click in the GUI.
>
> Please feel free to ask questions on any of the above. I can give some light support, but I expect y'all to be able to figure it out. If one of you two has the interest, it might be beneficial to become the team's "AWS expert". Lots of cool tech to learn there.
>
> I say one of you two, because you two have the real administrative access through your cisco laptops.

## Open decisions

- AWS region
- AWS lead
- Team access arrangements
