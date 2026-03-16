import { Amplify } from 'aws-amplify';

export function configureAuth() {
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: 'YOUR_COGNITO_USER_POOL_ID',
        userPoolClientId: 'YOUR_COGNITO_CLIENT_ID',
      },
    },
  });
}
