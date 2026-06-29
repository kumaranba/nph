import { gql } from "@apollo/client";

export const LOGIN = gql`
  mutation Login($email: String!, $password: String!) {
    login(email: $email, password: $password) {
      accessToken
      refreshToken
    }
  }
`;

export const ME = gql`
  query Me {
    me {
      id
      email
      role
    }
  }
`;

export const SEARCH_PATIENTS = gql`
  query SearchPatients($query: String!) {
    searchPatients(query: $query) {
      id
      patientId
      name
      guardianName
      guardianPhone
      admissionDate
      room
      bed
      feeStatus
    }
  }
`;
