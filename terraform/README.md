# Terraform — AWS VPC + EKS for DataDrift

Provisions the AWS infrastructure the Helm chart runs on, using plain `aws_*` resources so each piece is visible:

| File | What it creates |
|------|-----------------|
| `vpc.tf` | VPC, 2 public + 2 private subnets across 2 AZs, internet gateway, NAT gateway, route tables |
| `iam.tf` | IAM roles for the EKS control plane and the worker nodes |
| `eks.tf` | EKS cluster, a managed node group (2–4 × t3.medium) in the private subnets, and the EBS CSI + metrics-server add-ons |
| `outputs.tf` | VPC/subnet IDs, cluster endpoint, and the `aws eks update-kubeconfig` command |

## Real AWS account

```bash
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
terraform apply
aws eks update-kubeconfig --region ap-south-1 --name datadrift-eks
terraform destroy        # always, when finished: EKS + NAT gateway cost money every hour
```

## Without an AWS account (demo)

`offline_plan=true` skips the AWS credential checks so the plan can be shown with dummy keys. Nothing is created and no AWS API is called.

```bash
terraform init
terraform validate
AWS_ACCESS_KEY_ID=demo AWS_SECRET_ACCESS_KEY=demo terraform plan -var offline_plan=true
```
