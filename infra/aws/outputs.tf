output "alb_dns_name" {
  description = "Public DNS name of the Application Load Balancer. Point your domain's A/ALIAS record here."
  value       = aws_lb.app.dns_name
}

output "ecr_repo_url" {
  description = "URL of the ECR repository that stores backend images."
  value       = aws_ecr_repository.repo.repository_url
}
