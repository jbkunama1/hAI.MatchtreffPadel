pipeline {
    agent any
    stages {
        stage('Build') {
            steps {
                script {
                    echo "Building ${env.GITHUB_REPOSITORY} on branch ${env.BRANCH_NAME}"
                }
            }
        }
        stage('Test') {
            steps {
                script {
                    echo "Running tests..."
                }
            }
        }
    }
}
