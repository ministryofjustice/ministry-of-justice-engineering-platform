# Ministry of Justice Engineering Platform

[![Ministry of Justice Repository Compliance Badge](https://github-community.service.justice.gov.uk/repository-standards/api/ministry-of-justice-engineering-platform/badge)](https://github-community.service.justice.gov.uk/repository-standards/ministry-of-justice-engineering-platform)

This repository provides centralized, reusable GitHub Actions workflows and automation for the Ministry of Justice Developer Experience (DevX) team.

## Purpose

This repository centralizes ownership of reusable GitHub workflows to:
- Improve consistency across MoJ repositories
- Reduce duplication and drift between teams
- Enable standardization of CI/CD and automation patterns
- Provide DevX-owned automation for GitHub organization management

## Workflows

This repository provides several categories of workflows:

### Member Management
- **Add Members to Root Team (MoJ)** - Automated workflow that ensures GitHub organization members are added to root team for `ministryofjustice` organization
- **Add Members to Root Team (MoJAS)** - Automated workflow that ensures GitHub organization members are added to root team for `moj-analytical-services` organization

### CI/CD
- **Dependency Review** - Security scanning for dependency vulnerabilities in pull requests
- **Lint** - Validates GitHub Actions workflows, Markdown, and YAML files on pull requests
- **OpenSSF Scorecard** - Publishes repository security posture results to GitHub code scanning
- **Python Tests** (Reusable) - Reusable workflow for running Python unit tests with Pipenv

For detailed documentation, operational guidance, and troubleshooting, see the [Workflows Runbook](docs/WORKFLOWS_RUNBOOK.md).

## Using Reusable Workflows

Other MoJ repositories can use these workflows by referencing them in their own workflow files:

The member-sync reusable workflow checks out this repository at the same ref as the called workflow so `scripts/add_users_all_org_members_github_team.py` is always available when consumed cross-repo.

```yaml
jobs:
  add-members:
    uses: ministryofjustice/ministry-of-justice-engineering-platform/.github/workflows/reusable-add-members-to-root-team.yml@abb20ab0f42c5344f0479a4a5d931a1d72d9278e
    with:
      organization-name: "ministryofjustice"
      python-version: "3.11"
    secrets:
      app-id: ${{ secrets.APP_ID }}
      app-private-key: ${{ secrets.APP_PRIVATE_KEY }}
      slack-webhook-url: ${{ secrets.SLACK_WEBHOOK_URL }}
```

## Included Files

The repository comes with the following preset files:

- LICENSE
- .gitignore
- CODEOWNERS
- dependabot.yml
- GitHub Actions workflows (see [Workflows Runbook](docs/WORKFLOWS_RUNBOOK.md))

## Contributing

Contributions to improve workflows or add new reusable patterns are welcome. Please:

1. Create a feature branch
2. Make your changes
3. Test workflows thoroughly
4. Update documentation
5. Submit a pull request

## Standards Compliance

This repository follows the [Ministry of Justice GitHub Repository Standards](https://github-community.service.justice.gov.uk/repository-standards/guidance).

## Support

For questions or issues:
- Open an issue in this repository
- Contact the DevX Engineering Platform team
