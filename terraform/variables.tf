variable "project" {
  description = "Project name, used as a prefix for every resource."
  type        = string
  default     = "datadrift"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)."
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "ap-south-1"
}

variable "availability_zones" {
  description = "Two availability zones in aws_region; one public and one private subnet is created in each."
  type        = list(string)
  default     = ["ap-south-1a", "ap-south-1b"]

  validation {
    condition     = length(var.availability_zones) >= 2
    error_message = "EKS needs subnets in at least two availability zones."
  }
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.30.0.0/16"
}

variable "cluster_name" {
  description = "Name of the EKS cluster."
  type        = string
  default     = "datadrift-eks"
}

variable "kubernetes_version" {
  description = "EKS control plane version."
  type        = string
  default     = "1.35"
}

variable "node_instance_types" {
  description = "EC2 instance types for the managed node group."
  type        = list(string)
  default     = ["t3.medium"]
}

variable "node_desired_size" {
  type    = number
  default = 2
}

variable "node_min_size" {
  type    = number
  default = 2
}

variable "node_max_size" {
  type    = number
  default = 4
}

variable "offline_plan" {
  description = "Skip AWS credential checks so `terraform plan` can be demonstrated without an AWS account."
  type        = bool
  default     = false
}
