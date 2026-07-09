# ===========================================================================
# AgentPulse backend – common variables for AWS infrastructure
# ===========================================================================

variable "aws_region" {
  description = "AWS region where resources will be created."
  type        = string
}

variable "aws_account_id" {
  description = "AWS account ID that owns the resources."
  type        = string
}

variable "service_name" {
  description = "Name for the ECS service, cluster, and ECR repo."
  type        = string
  default     = "agentpulse-backend"
}

variable "container_image" {
  description = "Full image URI including tag (e.g. 439855819631.dkr.ecr.us-east-2.amazonaws.com/agentpulse-backend:abc123)."
  type        = string
}
