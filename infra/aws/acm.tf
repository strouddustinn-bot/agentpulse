################################################################################
# ACM certificate for api.agentpulse.ca + DNS validation via Cloudflare
################################################################################

resource "aws_acm_certificate" "api" {
  domain_name       = "api.${var.cloudflare_zone}"
  validation_method = "DNS"
  lifecycle {
    create_before_destroy = true
  }
}

# Validation CNAME records in Cloudflare
resource "cloudflare_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.api.domain_validation_options :
    dvo.domain_name => {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  }

  zone_id = data.cloudflare_zone.this.id
  name    = each.value.name
  type    = each.value.type
  value   = each.value.value
  ttl     = 300
  proxied = false  # must be DNS-only for validation
}

resource "aws_acm_certificate_validation" "api" {
  certificate_arn         = aws_acm_certificate.api.arn
  validation_record_fqdns = [for r in cloudflare_record.cert_validation : r.hostname]
}
