variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "ap-south-1"
}

variable "project" {
  description = "Lowercase prefix for resource names."
  type        = string
  default     = "ticketdesk"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,19}$", var.project))
    error_message = "Use 3-20 lowercase letters, digits or hyphens, starting with a letter."
  }
}

variable "environment" {
  description = "Environment tag."
  type        = string
  default     = "poc"
}

variable "repo_url" {
  description = "HTTPS clone URL of the TicketDesk repository (must contain no secrets)."
  type        = string

  validation {
    condition     = startswith(var.repo_url, "https://")
    error_message = "repo_url must be an https:// clone URL."
  }
}

variable "repo_branch" {
  description = "Branch the EC2 instance deploys."
  type        = string
  default     = "main"
}

variable "allowed_http_cidr" {
  description = "Who may reach the app on port 80. Use your own IP as x.x.x.x/32."
  type        = string

  validation {
    condition     = can(cidrhost(var.allowed_http_cidr, 0))
    error_message = "allowed_http_cidr must be a CIDR block such as 203.0.113.10/32."
  }
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Optional: two AZs for the private subnets. Empty = first two available."
  type        = list(string)
  default     = []
}

variable "instance_type" {
  type    = string
  default = "t3.micro"
}

variable "db_instance_class" {
  type    = string
  default = "db.t3.micro"
}

variable "db_backup_retention_days" {
  description = "Automated RDS backup retention (stretch goal: backup strategy)."
  type        = number
  default     = 7
}

variable "max_upload_mb" {
  type    = number
  default = 10
}

variable "alert_email" {
  description = "Email for CloudWatch alarm notifications. Leave empty to skip the subscription."
  type        = string
  default     = ""
}

variable "github_repository" {
  description = "owner/name of the GitHub repo allowed to deploy through GitHub Actions (OIDC). Empty disables it."
  type        = string
  default     = ""
}

variable "create_github_oidc_provider" {
  description = "Create the GitHub OIDC identity provider. Set false if your account already has one."
  type        = bool
  default     = true
}

variable "force_destroy_bucket" {
  description = "Let terraform destroy delete the attachments bucket including all object versions (POC teardown)."
  type        = bool
  default     = true
}
