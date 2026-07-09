# Deploying the AgentPulse backend on AWS (Fargate)

This document summarises the AWS resources created by the Terraform code in `infra/aws` and how the GitHub Actions workflow works.

## What Terraform creates

| Resource | Notes |
|----------|-------|
| **ECR repository** | `agentpulse-backend` – stores the container image. |
| **ECS Cluster** | Fargate, one service called `agentpulse-backend`. |
| **Task Definition** | 1 vCPU / 2 GB, container listens on port **8000**. |
| **ALB (HTTP)** | Public, forwards `:80` → task `:8000`. |
| **Log group** | `/ecs/agentpulse-backend` (14-day retention). |
| **Security groups** | ALB (public), Task (internal). |

HTTPS & a custom domain can be added later by attaching an ACM certificate and an extra `aws_lb_listener` on port 443.

## GitHub Actions – `deploy_backend.yml`

1. Builds the Docker image from `backend/Dockerfile`.
2. Pushes it to **Amazon ECR** with the commit SHA tag.
3. Runs `terraform apply` using OIDC-based AWS credentials.
   * Environment variables override the image URI + region.
4. Outputs the ALB DNS name (see the workflow summary). Point `agentpulse.com` (or a sub-domain) to this address using an **ALIAS** / **A** record.

## One-time setup

1. **Create an IAM role** for GitHub OIDC with the following policies:
   * `AmazonEC2ContainerRegistryFullAccess`
   * `AmazonECS_FullAccess`
   * `CloudWatchLogsFullAccess`
   * `ElasticLoadBalancingFullAccess`
   * (optionally restrict to specific resources once stabilised)
2. Add the role ARN as the repo secret `AWS_ROLE_TO_ASSUME`.
3. (Optional) Import an existing `agentpulse-backend` ECR repo with `terraform import` if you already created one manually.

## Next steps

* **HTTPS** – request an ACM certificate for `api.agentpulse.com`, create a Route 53 record, then add a port `443` listener in Terraform.
* **Autoscaling** – attach an `aws_appautoscaling_target` + policy to scale tasks 1→N based on CPU or request count.
* **RDS Postgres** – swap SQLite for Postgres when you outgrow a single container.
