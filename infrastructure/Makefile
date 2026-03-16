.PHONY: build_handlers clean upload_handlers build_template deploy_stack update_handlers deploy_frontend deploy_all smoke_test

# Variables
CODE_BUCKET := altum-deployment-assets
HANDLER_ZIP := dist/dashboard-handlers.zip
STACK_NAME := agent-dashboard-infrastructure
INFRASTRUCTURE_TEMPLATE := templates/infrastructure.yaml
TEMPLATE_S3_KEY := agent-dashboard-infrastructure.yaml
TEMPLATE_URL := https://$(CODE_BUCKET).s3.amazonaws.com/$(TEMPLATE_S3_KEY)
TEMP_BUILD_DIR := build_temp
PYTHON := python3
CERTIFICATE_ARN := YOUR_ACM_CERTIFICATE_ARN

# Build handlers package
build_handlers: clean
	@echo "Creating deployment package..."
	mkdir -p dist
	rm -rf $(TEMP_BUILD_DIR)
	mkdir -p $(TEMP_BUILD_DIR)
	@if [ -s handlers-requirements.txt ]; then \
		echo "Installing dependencies..."; \
		$(PYTHON) -m pip install -r handlers-requirements.txt -t $(TEMP_BUILD_DIR); \
	else \
		echo "No dependencies to install (handlers-requirements.txt is empty)"; \
	fi
	@echo "Copying handlers and modules..."
	@if [ -d handlers ]; then rsync -av handlers/ $(TEMP_BUILD_DIR)/handlers/; fi
	@if [ -d modules ]; then rsync -av modules/ $(TEMP_BUILD_DIR)/modules/; fi
	@echo "Creating zip archive..."
	cd $(TEMP_BUILD_DIR) && zip -r ../$(HANDLER_ZIP) .
	rm -rf $(TEMP_BUILD_DIR)
	@echo "Deployment package created at $(HANDLER_ZIP)"

# Clean build artifacts
clean:
	rm -rf $(TEMP_BUILD_DIR) dist

# Upload handlers to S3
upload_handlers: build_handlers
	@echo "Uploading handlers to S3..."
	aws s3 cp $(HANDLER_ZIP) s3://$(CODE_BUCKET)/dashboard-handlers.zip

# Build SAM template from fragments
build_template:
	@echo "Building template from fragments..."
	$(PYTHON) templates/build_template.py

# Deploy CloudFormation stack
deploy_stack: build_template
	@echo "Uploading CloudFormation template..."
	@aws s3 cp $(INFRASTRUCTURE_TEMPLATE) s3://$(CODE_BUCKET)/$(TEMPLATE_S3_KEY)
	@echo "Retrieving latest version..."
	@LATEST_VERSION=$$(aws s3api list-object-versions --bucket $(CODE_BUCKET) --prefix dashboard-handlers.zip --query 'Versions[?IsLatest==`true`].VersionId' --output text 2>/dev/null); \
	echo "  dashboard-handlers.zip: $$LATEST_VERSION"; \
	if aws cloudformation describe-stacks --stack-name $(STACK_NAME) >/dev/null 2>&1; then \
	  echo "Updating CloudFormation stack..."; \
	  aws cloudformation update-stack --stack-name $(STACK_NAME) --template-url $(TEMPLATE_URL) --capabilities CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND --parameters ParameterKey=HandlersVersion,ParameterValue=$$LATEST_VERSION ParameterKey=CertificateArn,ParameterValue=$(CERTIFICATE_ARN) || true; \
	else \
	  echo "Creating CloudFormation stack..."; \
	  aws cloudformation create-stack --stack-name $(STACK_NAME) --template-url $(TEMPLATE_URL) --capabilities CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND --parameters ParameterKey=HandlersVersion,ParameterValue=$$LATEST_VERSION ParameterKey=CertificateArn,ParameterValue=$(CERTIFICATE_ARN); \
	fi

# Update handlers and deploy stack
update_handlers: upload_handlers deploy_stack

# Deploy frontend to S3
deploy_frontend:
	@echo "Building frontend..."
	cd frontend && npm run build
	@echo "Syncing frontend to S3..."
	aws s3 sync frontend/dist/ s3://agent-dashboard-frontend/ --delete

# Deploy everything
deploy_all: update_handlers deploy_frontend
	@echo "Full deployment completed"

# Run smoke test against deployed API
smoke_test:
	$(PYTHON) tests/smoke_test.py
