# Remote state for a team setup. Create the bucket once, then uncomment and run `terraform init -migrate-state`.
# Local state is fine for a single-person demo.
#
# terraform {
#   backend "s3" {
#     bucket       = "datadrift-terraform-state"
#     key          = "eks/terraform.tfstate"
#     region       = "ap-south-1"
#     encrypt      = true
#     use_lockfile = true
#   }
# }
