terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }

  # State is kept locally (terraform.tfstate, git-ignored) for the POC.
  # For a team, move it to an S3 backend with a lock table, e.g.:
  # backend "s3" {
  #   bucket         = "<state-bucket>"
  #   key            = "ticketdesk/terraform.tfstate"
  #   region         = "ap-south-1"
  #   dynamodb_table = "<lock-table>"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "TicketDesk"
      ManagedBy = "Terraform"
      Env       = var.environment
    }
  }
}
