# Backend configuration for Terraform state
# Uncomment and configure if you want to use remote state

# terraform {
#   backend "s3" {
#     bucket         = "vaani-terraform-state"
#     key            = "vaani/terraform.tfstate"
#     region         = "ap-south-1"
#     encrypt        = true
#     dynamodb_table = "vaani-terraform-locks"
#   }
# }
