################################################################################
# Cloudflare DNS integration – manages api.agentpulse.ca CNAME -> ALB
################################################################################

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

################################################################################
# Zone lookup
################################################################################

data "cloudflare_zone" "this" {
  name = var.cloudflare_zone
}

################################################################################
# CNAME record: api.agentpulse.ca -> ALB DNS name
################################################################################
resource "cloudflare_record" "api_cname" {
  zone_id = data.cloudflare_zone.this.id
  name    = "api"
  type    = "CNAME"
  value   = aws_lb.app.dns_name
  ttl     = 300
  proxied = var.cf_proxy
}
