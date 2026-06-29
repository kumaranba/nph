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

// Only vacant beds — used to populate the admission form's bed picker.
export const VACANT_BEDS = gql`
  query VacantBeds {
    beds(status: "VACANT") {
      id
      label
      room {
        id
        name
      }
    }
  }
`;

export const CREATE_ADMISSION = gql`
  mutation CreateAdmission($input: CreateAdmissionInput!) {
    createAdmission(input: $input) {
      id
      status
      patient {
        id
        patientId
        name
      }
      bed {
        id
        label
        status
      }
    }
  }
`;

// A single patient (with admissions), used by the patient profile page.
export const PATIENT = gql`
  query Patient($pk: ID!) {
    patient(pk: $pk) {
      id
      patientId
      name
      age
      diagnosis
      guardianName
      guardianPhone
      admittingDoctor
      createdAt
      admissions {
        id
        status
        admissionDate
        hasOutstandingDues
        outstandingInvoiceCount
        bed {
          id
          label
          room {
            id
            name
          }
        }
      }
    }
  }
`;

export const DISCHARGE_PATIENT = gql`
  mutation DischargePatient($admissionId: ID!, $refundAmount: Decimal) {
    dischargePatient(admissionId: $admissionId, refundAmount: $refundAmount) {
      hasOutstandingDues
      outstandingInvoiceCount
      refundAmount
      admission {
        id
        status
        dischargeDate
      }
    }
  }
`;
