# SGTM
One-way sync of GitHub pull requests to Asana tasks so engineers can track all of their work in Asana. To see a more detailed explanation of the functionality of SGTM, see the [code_reviews](docs/code_reviews.md) docs.

## Setup
Follow these instructions for setting up SGTM to run in your environment and your infrastructure! Note that this is currently only set up for deployment on AWS, so if you are using a cloud provider, you may need to modify some code and deploy the app yourself.

### Fork repository and set up your local repository
You will need to set some overrides specific to your deployment -- mostly due to the fact that AWS S3 bucket names are globally unique, but you may want to tweak some default configuration settings. So, we recommend forking this repository into your Github organization.

### Installation
We recommend setting up a virtual environment to install and run your python environment. By doing so, you can eliminate
the risk that SGTM's python dependencies and settings will be mixed up with any such dependencies and settings that you
may be using in other projects. Once you have that activated (see [Installing a Virtual Environment for Python](#installing-a-virtual-environment-for-python) below),
you should install all required python dependencies using `pip3 install -r requirements.txt -r requirements-dev.txt`.

### Install Terraform
You'll need to [install Terraform](https://learn.hashicorp.com/tutorials/terraform/install-cli) to launch the infrastructure for SGTM.

### Install Terragrunt
You'll need to [install Terragrunt](https://terragrunt.gruntwork.io/docs/getting-started/install/) to configure Terraform for your own account.

### Create your credentials for Asana/AWS/Github
There are three external services you'll need to interact with, and therefore need credentials for.

#### Asana
Create a [Personal Access Token](https://developers.asana.com/docs/personal-access-token) in Asana. At Asana, we created a [Guest Account](https://asana.com/guide/help/organizations/guests) to run SGTM as, so no engineer's personal access token is used, and it's clear that there's a specific "SGTM" user who is making the task updates.

Copy this Personal Access Token for the next step.

#### AWS
You'll need to be able to authenticate with AWS via the command line, and there are a few ways to achieve that. See [here](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html) for your options, but most likely you'll already have a preferred method of interacting with AWS via the command line.

#### Github
Again, you will probably want to create a new Github user in your org that is just for SGTM (since SGTM will be updating/merging PRs, it's clearer to attribute those actions to a user that is clearly name "SGTM" or something similar).

1. For the Github user you want to use, generate a [Personal Access Token](https://docs.github.com/en/github/authenticating-to-github/creating-a-personal-access-token) with the following permissions:
   * repo (Full control of private repositories)
   * read:org (Read org and team membership, read org projects)
2. Generate a [secret token](https://developer.github.com/webhooks/securing/) for your Github webhook. Github suggests generating this via `ruby -rsecurerandom -e 'puts SecureRandom.hex(20)'`, but use whatever method you are comfortable with to generate a secure secret token. Save this somewhere, as you'll need it twice in the later steps.

Copy this Personal Accesss Token for the next step.

### Create Asana Projects
You'll need to create two Asana projects: one that will store the mapping of Github username to Asana user id, and the other where your Github sync tasks will live.

1. Create your "SGTM Users" project (feel free to name this whatever you want -- this is just a suggestion). The requirements of this project are two custom fields named: "Github Username" (Text field) and "user_id" (Number field). Save the `id` of this project (from the URL once created) in `./terraform/terraform.tfvars.json` under `"asana_users_project_id"`.
2. To create your "SGTM <repo> tasks" project, use the `setup_sgtm_tasks_project.py` script. The script will prompt you for the PAT you generated earlier, and guide you through setting up a brand new project or updating an existing project with the recommended Custom Fields.
     ```
      >>> To setup a new project
      python3 scripts/setup_sgtm_tasks_project.py  -p "<PAT>" create -n "<PROJECT NAME>" -t "<TEAM ID>"
           
      >>> To update an existing project with the suggested custom fields
      python3 scripts/setup_sgtm_tasks_project.py  -p "<PAT>" update -e "<EXISTING PROJECT ID>"
      ```
    1. If you have multiple repositories you want synced to Asana, you can create several of these projects. Make sure to take note of all of the project IDs for a later step.
    2. If you are on Asana Basic and do not have access to Custom Fields, the script will skip that step - SGTM will work even without the suggested fields
3. Make sure that the Asana user/guest that you created earlier is a member of both of these projects.

### Set your Terraform variables
NOTE: AWS S3 Bucket names are globally unique, so you will need to choose your own bucket names to be unique that no other AWS account has already created.
1. In `./terraform/variables.tf`, any variable that is listed without a default value needs to be set. The preferred method of setting these values is through [environment variables](https://www.terraform.io/docs/cli/config/environment-variables.html#tf_var_name). For example, to se terraform variable `asana_users_project_id`, you'll want to set an environment variable `TF_VAR_asana_users_project_id`.
2. Save these somewhere that you and others collaborating on this deployment could share (we save ours in an Asana task internally, of course) since these will need to be the same each time you apply new changes.

### Zip up your code
From the root of your repository directory, run `./scripts/zip_lambda_code.sh`. This will zip up all of the Python code and dependencies to be pushed to AWS in the next step (the `terraform apply`)

### Run setup script
You'll first need to set up the [Terraform remote state](https://www.terraform.io/docs/state/remote.html) to be the source of truth for the state of your deployed infrastructure.

1. Run `python3 ./scripts/setup.py state` (this will create  an S3 bucket and DyanmoDb lock table for Terraform)
2. Initialize and apply the infrastructure:
```bash
> cd ./terraform
> terragrunt init
> terragrunt apply
```
1. Save the output of `terragrunt apply`, which should print out a `api_gateway_deployment_invoke_url`. You'll need this in the next step.
1. Push your secrets to the ecrypted S3 bucket that Terraform just created. `cd` back to the root of your repository and run: `python3 ./scripts/setup.py secrets` and follow the prompts.

### Add Mapping of Github Repository -> Asana Project
For each repository that you are going to sync:
1. Find that repository's Github Graphql `node_id`:
   1. You can get this using `curl -i -u <username>:<github_personal_access_token> https://api.github.com/repos/<organization>/<repository>`
1. Using the "SGTM tasks" project id from [Create Asana Projects](#create-asana-projects), update the sgtm-objects DynamoDb table with the mapping of `{"github-node": "<node_id>", "asana-id": "<project_id>"}`

### Create Your Github Webhook
For each repository that you want to sync to Asana through SGTM:
1. Navigate to `https://github.com/<organization>/<repository>/settings/hooks`
1. Click "Add webhook"
1. Under "Payload URL", input the `api_gateway_deployment_invoke_url` from the previous step
1. Under "Content Type", select "application/json"
1. Under "Secret", input your secret token that you generated earlier
1. Under "Which events would you like to trigger this webhook?", select "Let me select individual events."
   1. Issue comments
   1. Pull requests
   1. Pull request reviews
   1. Pull request review comments
   1. Statuses
1. Make sure "Active" is selected
1. Click "Add webhook"

### Take it for a spin!
At this point, you should be all set to start getting Pull Requests synced to Asana Tasks. Open up a Pull Request, and Enjoy!

## Optional Features
SGTM has a few optional power features that are disabled by default, but can be enabled with environment variables.
### Auto-merge pull requests
SGTM can merge your pull requests automatically when certain conditions are fulfilled. This behavior is controlled by adding labels to the PR in Github. If this feature is enabled, there are 3 different labels you can apply to your PR to cause the PR to be auto-merged under different conditions:
* 🔍 `merge after tests and approval`: auto-merge this PR once tests pass and the PR is approved
* 🧪 `merge after tests`: auto-merge this PR once tests pass (regardless of approval status)
* 🚢 `merge immediately`: auto-merge this PR immediately

In all cases, a PR with merge conflicts will not be auto-merged.

**How to enable**:
* Set an env variable of `TF_VAR_sgtm_feature__automerge_enabled` to `true`
* Create labels in your repository of `merge after tests and approval`, `merge after tests` and `merge immediately`

### Auto-complete linked tasks
At Asana, pull requests often have corresponding Asana tasks that can be completed when the pull request merges. With this feature enabled, setting a Github label of `complete tasks on merge` on a PR will automatically complete any linked Asana tasks. Asana tasks can be linked by adding their URLs to a line under the string `Asana tasks:` in the PR description, as demonstrated below:
```
Asana tasks:
<task_to_complete_url> <another_task_to_complete_url>
```
**How to enable**:
* Set an env variable of `TF_VAR_sgtm_feature__autocomplete_enabled` to `true`
* Create a label of `complete tasks on merge` in your repository

*Note*: If the SGTM user in your Asana domain doesn't have access to a linked task, it won't be able to merge it. You can add the SGTM user as a collaborator on a task to give it the ability to auto-complete the task.

## Installing a Virtual Environment for Python

See [these instructions](https://packaging.python.org/guides/installing-using-pip-and-virtual-environments/) for help in
setting up a virtual environment for Python, or use the following TL;DR version:

* run `python3 -m venv v-env` to create a virtual environment
* run `source v-env/bin/activate` to activate and enter your virtual environment
* once activated, run `deactivate` to deactivate and leave your virtual environment

## Running Tests

To run the tests, you must set the AWS_DEFAULT_REGION environment variable. This is required because some of the tests
are integration tests that require DynamoDb. This needs to be exported, so that it is available to sub-processes. Here's how:
```bash
if [ -z "$AWS_DEFAULT_REGION" ]; then export AWS_DEFAULT_REGION="us-east-1"; else export AWS_DEFAULT_REGION=$AWS_DEFAULT_REGION; fi
```

You may then run all tests via the command line:

```bash
python3 -m unittest discover
```

Alternatively, you may run specific tests e.g. via:

```bash
python3 ./test/<python-test-file-name>.py>
python3 ./test/<python-test-file-name>.py> <TestClassName>
python3 ./test/<python-test-file-name>.py> <TestClassName.test_function_name>
```

## "Building"

Please perform the following checks prior to pushing code

* run `black .` to autoformat your code
* run `mypy` on each file that you have changed
* run tests, as described in the previous section
