# Security groups. No SSH: administration is through SSM Session Manager.

variable "name" { type = string }
variable "vpc_id" { type = string }
variable "allowed_http_cidr" { type = string }

resource "aws_security_group" "app" {
  name        = "${var.name}-app-sg"
  description = "TicketDesk web server: HTTP from the allowed CIDR only, no SSH"
  vpc_id      = var.vpc_id
  tags        = { Name = "${var.name}-app-sg" }
}

resource "aws_vpc_security_group_ingress_rule" "app_http" {
  security_group_id = aws_security_group.app.id
  description       = "HTTP to nginx"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = var.allowed_http_cidr
}

# Outbound HTTPS: package installs, git clone, Docker images, and AWS APIs
# (S3, Secrets Manager, CloudWatch Logs, SSM).
resource "aws_vpc_security_group_egress_rule" "app_https" {
  security_group_id = aws_security_group.app.id
  description       = "HTTPS to package mirrors and AWS APIs"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

# Amazon Linux 2023 package mirrors are reached over HTTP as well as HTTPS.
resource "aws_vpc_security_group_egress_rule" "app_http_out" {
  security_group_id = aws_security_group.app.id
  description       = "HTTP to package mirrors"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "app_to_db" {
  security_group_id            = aws_security_group.app.id
  description                  = "PostgreSQL to RDS"
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  referenced_security_group_id = aws_security_group.db.id
}

resource "aws_security_group" "db" {
  name        = "${var.name}-db-sg"
  description = "TicketDesk RDS: PostgreSQL from the app security group only"
  vpc_id      = var.vpc_id
  tags        = { Name = "${var.name}-db-sg" }
}

resource "aws_vpc_security_group_ingress_rule" "db_from_app" {
  security_group_id            = aws_security_group.db.id
  description                  = "PostgreSQL from the TicketDesk EC2 instance"
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  referenced_security_group_id = aws_security_group.app.id
}

output "app_security_group_id" { value = aws_security_group.app.id }
output "db_security_group_id" { value = aws_security_group.db.id }
