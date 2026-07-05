import { gql } from "@apollo/client";

/**
 * Dashboard GraphQL operations.
 *
 * Only FEES_DUE_LIST (in operations.ts) maps to a resolver that already exists.
 * The queries below need matching backend resolvers — see README.md for the
 * exact field contract each one expects. Until they exist the relevant panel
 * will render its <QueryError> state; the rest of the dashboard is unaffected
 * because every widget fetches independently.
 */

export const DASHBOARD_STATS = gql`
  query DashboardStats {
    dashboardStats {
      bedsOccupied
      bedsTotal
      outstandingTotal
      outstandingInvoiceCount
      overdueCount
      feesDueTotal
      feesDueCount
      feesDueToday
      flaggedVitalsCount
      flaggedPatientCount
      criticalCount
    }
  }
`;

export const PAYMENTS_TREND = gql`
  query PaymentsTrend($months: Int) {
    paymentsTrend(months: $months) {
      month
      total
    }
  }
`;

export const FLAGGED_VITALS_FEED = gql`
  query FlaggedVitalsFeed($limit: Int) {
    flaggedVitals(limit: $limit) {
      id
      patientName
      room
      vital
      value
      direction
      severity
      recordedAt
    }
  }
`;

export const RECENT_ADMISSIONS = gql`
  query RecentAdmissions($limit: Int) {
    recentAdmissions(limit: $limit) {
      id
      admissionDate
      admittingDoctor
      patient {
        id
        patientId
        name
        age
        diagnosis
      }
      bed {
        label
        room {
          name
        }
      }
    }
  }
`;

export const WARD_OCCUPANCY = gql`
  query WardOccupancy {
    wards {
      id
      name
      beds {
        id
        label
        status
      }
    }
  }
`;

export const ACTIVITY_LOG = gql`
  query ActivityLog($limit: Int) {
    activityLog(limit: $limit) {
      id
      kind
      message
      actor
      createdAt
    }
  }
`;
