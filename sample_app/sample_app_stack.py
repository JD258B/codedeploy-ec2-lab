from aws_cdk import core as cdk
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_elasticloadbalancingv2 as elb
import aws_cdk.aws_autoscaling as autoscaling
import aws_cdk.aws_iam as iam
import aws_cdk.aws_s3 as s3
import aws_cdk.aws_s3_deployment as s3_deploy
import aws_cdk.aws_codedeploy as codedeploy

inst_type = 't2.micro'
ami = ec2.AmazonLinuxImage(
    generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2,
    edition=ec2.AmazonLinuxEdition.STANDARD,
    virtualization=ec2.AmazonLinuxVirt.HVM,
    storage=ec2.AmazonLinuxStorage.GENERAL_PURPOSE
)

with open('./user_data/user_data.sh') as f:
    user_data = f.read()

class SampleAppStack(cdk.Stack):

    def __init__(self, scope: cdk.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        app_artifact_bucket = s3.Bucket(self, 'app-artifact-bucket',
            auto_delete_objects=True, removal_policy=cdk.RemovalPolicy.DESTROY
        )

        s3_artifacts = s3_deploy.BucketDeployment(self, 'sample-app-deployment',
            destination_bucket=app_artifact_bucket,
            sources=[s3_deploy.Source.asset('./artifacts')]
        )

        app_role = iam.Role(self, 'sample-app-role', 
            assumed_by=iam.ServicePrincipal('ec2.amazonaws.com'),
            role_name='sample-app-role'        
        )

        app_policy = iam.Policy(self, 'sample-app-s3-read',
            roles=[app_role],
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        's3:Get*',
                        's3:List*'
                    ],
                    resources=[
                        'arn:aws:s3:::aws-codedeploy-us-east-1/*',
                        app_artifact_bucket.bucket_arn,
                        app_artifact_bucket.bucket_arn + '/*'
                    ]
                )
            ]
        )

        codedeploy_role = iam.Role(self, 'codedeploy-role', 
            assumed_by=iam.ServicePrincipal('codedeploy.amazonaws.com'),
            role_name='codedeploy-role'
        )

        codedeploy_policy = iam.Policy(self, 'codedeploy-policy',
            roles=[codedeploy_role],
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        'iam:PassRole',
                        'ec2:CreateTags',
                        'ec2:RunInstances',
                        'autoscaling:CompleteLifecycleAction',
                        'autoscaling:DeleteLifecycleHook',
                        'autoscaling:DescribeAutoScalingGroups',
                        'autoscaling:DescribeLifecycleHooks',
                        'autoscaling:PutLifecycleHook',
                        'autoscaling:RecordLifecycleActionHeartbeat',
                        'autoscaling:CreateAutoScalingGroup',
                        'autoscaling:UpdateAutoScalingGroup',
                        'autoscaling:EnableMetricsCollection',
                        'autoscaling:DescribePolicies',
                        'autoscaling:DescribeScheduledActions',
                        'autoscaling:DescribeNotificationConfigurations',
                        'autoscaling:SuspendProcesses',
                        'autoscaling:ResumeProcesses',
                        'autoscaling:AttachLoadBalancers',
                        'autoscaling:AttachLoadBalancerTargetGroups',
                        'autoscaling:PutScalingPolicy',
                        'autoscaling:PutScheduledUpdateGroupAction',
                        'autoscaling:PutNotificationConfiguration',
                        'autoscaling:PutWarmPool',
                        'autoscaling:DescribeScalingActivities',
                        'autoscaling:DeleteAutoScalingGroup',
                        'ec2:DescribeInstances',
                        'ec2:DescribeInstanceStatus',
                        'ec2:TerminateInstances',
                        'tag:GetResources',
                        'sns:Publish',
                        'cloudwatch:DescribeAlarms',
                        'cloudwatch:PutMetricAlarm',
                        'elasticloadbalancing:DescribeLoadBalancers',
                        'elasticloadbalancing:DescribeInstanceHealth',
                        'elasticloadbalancing:RegisterInstancesWithLoadBalancer',
                        'elasticloadbalancing:DeregisterInstancesFromLoadBalancer',
                        'elasticloadbalancing:DescribeTargetGroups',
                        'elasticloadbalancing:DescribeTargetHealth',
                        'elasticloadbalancing:RegisterTargets',
                        'elasticloadbalancing:DeregisterTargets'
                    ],
                    resources=['*']
                )
            ]
        )

        app_vpc = ec2.Vpc(self, 'sample-app-vpc',
            cidr='10.0.0.0/16',
            max_azs=99,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    subnet_type=ec2.SubnetType.PUBLIC,
                    name='public-',
                    cidr_mask=24
                )
            ]
        )

        app_lb = elb.ApplicationLoadBalancer(self, 'sample-app-alb',
            vpc=app_vpc,
            internet_facing=True,
            load_balancer_name='sample-app-alb'
        )

        app_lb.connections.allow_from_any_ipv4(ec2.Port.tcp(80), 'Internet Access to ALB')

        app_lb_listener = app_lb.add_listener('http-listener', port=80, open=True)

        self.auto_scaling_group = autoscaling.AutoScalingGroup(self, 'sample-app-asg',
            vpc=app_vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            instance_type=ec2.InstanceType(instance_type_identifier=inst_type),
            machine_image=ami,
            auto_scaling_group_name='sample-app-asg',
            role=app_role,
            user_data=ec2.UserData.custom(user_data),
            health_check=autoscaling.HealthCheck.ec2(grace=cdk.Duration.seconds(300)),
            desired_capacity=4,
            min_capacity=4,
            max_capacity=8
        )

        self.auto_scaling_group.connections.allow_from(app_lb, ec2.Port.tcp(80), 'ALB to EC2 access')
        app_lb_listener.add_targets('sample-app-target-group', port=80, targets=[self.auto_scaling_group], target_group_name='sample-app-tg')

        asg_name = cdk.CfnOutput(self, 'AutoScaling Group Name',
            value=self.auto_scaling_group.auto_scaling_group_name,
            description='AutoScaling Group Name'
        )
        code_deploy_role_arn = cdk.CfnOutput(self, 'Codedeploy Role ARN',
            value=codedeploy_role.role_arn,
            description='CodeDeployRoleARN'
        )
        s3_bucket = cdk.CfnOutput(self, 'S3 Bucket Name',
            value=app_artifact_bucket.bucket_name,
            description='S3 Bucket Name' 
        )
        initial_deployment_object_url = cdk.CfnOutput(self, 'Initial S3 Object URL',
            value='s3://' + app_artifact_bucket.bucket_name + '/initial-deployment/Archive.zip',
            description='Initial Deployment S3 Object URL'
        )
        in_place_deployment_object_url = cdk.CfnOutput(self, 'In-Place S3 Object URL',
            value='s3://' + app_artifact_bucket.bucket_name + '/in-place/Archive.zip',
            description='In-Place Deployment S3 Object URL'
        )
        blue_green_deployment_object_url = cdk.CfnOutput(self, 'Blue Green S3 Object URL',
            value='s3://' + app_artifact_bucket.bucket_name + '/blue-green/Archive.zip',
            description='Initial Deployment S3 Object URL'
        )
        alb_url = cdk.CfnOutput(self, 'Load Balancer URL',
            value=app_lb.load_balancer_dns_name,
            description='Load Balancer URL'
        )
        