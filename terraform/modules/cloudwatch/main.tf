# Centralised app logs, an operations dashboard, and alarms (stretch goals).

variable "name" { type = string }
variable "aws_region" { type = string }
variable "app_log_group_name" { type = string }
variable "instance_id" { type = string }
variable "db_instance_id" { type = string }
variable "lambda_function_name" { type = string }
variable "lambda_log_group" { type = string }
variable "alert_email" { type = string }

locals {
  dashboard_name = "${var.name}-operations"
  metric_ns      = "TicketDesk"
}

# Container logs from the EC2 instance (Docker awslogs driver).
resource "aws_cloudwatch_log_group" "app" {
  name              = var.app_log_group_name
  retention_in_days = 14
}

# Count application ERROR lines as a metric so they can be alarmed on.
resource "aws_cloudwatch_log_metric_filter" "app_errors" {
  name           = "${var.name}-app-errors"
  log_group_name = aws_cloudwatch_log_group.app.name
  pattern        = "ERROR"

  metric_transformation {
    name          = "AppErrors"
    namespace     = local.metric_ns
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_log_metric_filter" "failed_logins" {
  name           = "${var.name}-failed-logins"
  log_group_name = aws_cloudwatch_log_group.app.name
  pattern        = "\"Failed login\""

  metric_transformation {
    name          = "FailedLogins"
    namespace     = local.metric_ns
    value         = "1"
    default_value = "0"
  }
}

# ------------------------------------------------------------------ alarms

resource "aws_sns_topic" "alerts" {
  name = "${var.name}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alert_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

locals {
  alarms = {
    ec2-cpu-high = {
      description = "EC2 CPU above 80% for 10 minutes"
      namespace   = "AWS/EC2", metric = "CPUUtilization", stat = "Average"
      dimensions  = { InstanceId = var.instance_id }
      comparison  = "GreaterThanThreshold", threshold = 80, periods = 2, period = 300
    }
    ec2-status-check = {
      description = "EC2 instance or system status check failing"
      namespace   = "AWS/EC2", metric = "StatusCheckFailed", stat = "Maximum"
      dimensions  = { InstanceId = var.instance_id }
      comparison  = "GreaterThanOrEqualToThreshold", threshold = 1, periods = 2, period = 60
    }
    rds-cpu-high = {
      description = "RDS CPU above 80% for 10 minutes"
      namespace   = "AWS/RDS", metric = "CPUUtilization", stat = "Average"
      dimensions  = { DBInstanceIdentifier = var.db_instance_id }
      comparison  = "GreaterThanThreshold", threshold = 80, periods = 2, period = 300
    }
    rds-storage-low = {
      description = "RDS free storage below 2 GB"
      namespace   = "AWS/RDS", metric = "FreeStorageSpace", stat = "Minimum"
      dimensions  = { DBInstanceIdentifier = var.db_instance_id }
      comparison  = "LessThanThreshold", threshold = 2147483648, periods = 1, period = 300
    }
    lambda-errors = {
      description = "File processor Lambda reported errors"
      namespace   = "AWS/Lambda", metric = "Errors", stat = "Sum"
      dimensions  = { FunctionName = var.lambda_function_name }
      comparison  = "GreaterThanOrEqualToThreshold", threshold = 1, periods = 1, period = 300
    }
    app-errors = {
      description = "TicketDesk logged 5 or more ERROR lines in 5 minutes"
      namespace   = local.metric_ns, metric = "AppErrors", stat = "Sum"
      dimensions  = {}
      comparison  = "GreaterThanOrEqualToThreshold", threshold = 5, periods = 1, period = 300
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "this" {
  for_each = local.alarms

  alarm_name          = "${var.name}-${each.key}"
  alarm_description   = each.value.description
  namespace           = each.value.namespace
  metric_name         = each.value.metric
  statistic           = each.value.stat
  dimensions          = each.value.dimensions
  comparison_operator = each.value.comparison
  threshold           = each.value.threshold
  evaluation_periods  = each.value.periods
  period              = each.value.period
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]

  depends_on = [aws_cloudwatch_log_metric_filter.app_errors]
}

# ------------------------------------------------------------------ dashboard

resource "aws_cloudwatch_dashboard" "this" {
  dashboard_name = local.dashboard_name
  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric", x = 0, y = 0, width = 8, height = 6
        properties = {
          title   = "EC2 CPU (%)", region = var.aws_region, view = "timeSeries", stat = "Average", period = 300
          metrics = [["AWS/EC2", "CPUUtilization", "InstanceId", var.instance_id]]
        }
      },
      {
        type = "metric", x = 8, y = 0, width = 8, height = 6
        properties = {
          title = "RDS connections and CPU", region = var.aws_region, view = "timeSeries", period = 300
          metrics = [
            ["AWS/RDS", "DatabaseConnections", "DBInstanceIdentifier", var.db_instance_id, { stat = "Maximum" }],
            ["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", var.db_instance_id, { stat = "Average", yAxis = "right" }],
          ]
        }
      },
      {
        type = "metric", x = 16, y = 0, width = 8, height = 6
        properties = {
          title = "Lambda file processor", region = var.aws_region, view = "timeSeries", stat = "Sum", period = 300
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", var.lambda_function_name],
            ["AWS/Lambda", "Errors", "FunctionName", var.lambda_function_name],
          ]
        }
      },
      {
        type = "metric", x = 0, y = 6, width = 8, height = 6
        properties = {
          title = "App errors and failed logins", region = var.aws_region, view = "timeSeries", stat = "Sum", period = 300
          metrics = [
            [local.metric_ns, "AppErrors"],
            [local.metric_ns, "FailedLogins"],
          ]
        }
      },
      {
        type = "metric", x = 8, y = 6, width = 8, height = 6
        properties = {
          title   = "RDS free storage (bytes)", region = var.aws_region, view = "timeSeries", stat = "Minimum", period = 300
          metrics = [["AWS/RDS", "FreeStorageSpace", "DBInstanceIdentifier", var.db_instance_id]]
        }
      },
      {
        type = "alarm", x = 16, y = 6, width = 8, height = 6
        properties = {
          title  = "Alarms"
          alarms = [for a in aws_cloudwatch_metric_alarm.this : a.arn]
        }
      },
      {
        type = "log", x = 0, y = 12, width = 24, height = 6
        properties = {
          title = "Recent attachment processing (Lambda)", region = var.aws_region, view = "table"
          query = "SOURCE '${var.lambda_log_group}' | fields @timestamp, key, size, detected_type, `processing-status`, reason | filter ispresent(key) | sort @timestamp desc | limit 20"
        }
      },
      {
        type = "log", x = 0, y = 18, width = 24, height = 6
        properties = {
          title = "Recent application warnings and errors", region = var.aws_region, view = "table"
          query = "SOURCE '${aws_cloudwatch_log_group.app.name}' | fields @timestamp, @logStream, @message | filter @message like /WARNING|ERROR/ | sort @timestamp desc | limit 20"
        }
      },
    ]
  })
}

output "app_log_group_name" { value = aws_cloudwatch_log_group.app.name }
output "app_log_group_arn" { value = aws_cloudwatch_log_group.app.arn }
output "dashboard_name" { value = aws_cloudwatch_dashboard.this.dashboard_name }
output "alerts_topic_arn" { value = aws_sns_topic.alerts.arn }
