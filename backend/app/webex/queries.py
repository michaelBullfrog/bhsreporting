TASK_QUERY = """
query($from: Long!, $to: Long!) {
  task(from: $from, to: $to) {
    tasks {
      id
      status
      channelType
      createdTime
      endedTime
      origin
      destination
      direction
      terminationType
      connectedCount
      connectedDuration
      holdCount
      holdDuration
      totalDuration
      lastWrapupCodeName
      lastQueue { id name duration }
      callbackData {
        callbackRequestTime
        callbackConnectTime
        callbackNumber
        callbackStatus
        callbackOrigin
        callbackType
        callbackQueueName
        callbackAgentName
        callbackTeamName
        callbackRetryCount
      }
    }
  }
}
"""

TASK_DETAILS_QUERY = """
query($from: Long!, $to: Long!) {
  taskDetails(from: $from, to: $to) {
    tasks {
      id
      status
      channelType
      createdTime
      endedTime
      direction
      terminationType
      lastWrapupCodeName
      lastAgent { id name signInId sessionId }
    }
  }
}
"""

TASK_LEG_DETAILS_QUERY = """
query($from: Long!, $to: Long!) {
  taskLegDetails(from: $from, to: $to) {
    taskLegs {
      id
      taskId
      status
      contactState
      createdTime
      endedTime
      origin
      destination
      channelType
      queue { id name duration }
      ringingDuration
      owner { id name signInId sessionId }
      connectedDuration
      holdCount
      holdDuration
      lastWrapupCodeName
      wrapupDuration
    }
  }
}
"""


# Initial session fetch. Inner AAR page size is explicitly raised to 100,
# which is the maximum supported by the WxCC Search API.
AGENT_SESSION_QUERY = """
query($from: Long!, $to: Long!, $cursor: String!) {
  agentSession(
    from: $from
    to: $to
    pagination: { cursor: $cursor }
  ) {
    agentSessions {
      agentSessionId
      agentId
      agentName
      teamName
      startTime
      endTime
      state
      channelInfo {
        channelId
        channelType
        totalDuration
        connectedDuration
        activities(first: 100) {
          totalCount
          pageInfo {
            endCursor
            hasNextPage
          }
          nodes {
            id
            startTime
            endTime
            state
          }
        }
      }
    }
    pageInfo {
      endCursor
      hasNextPage
    }
  }
}
"""

# Targeted inner pagination. Cisco documents that an inner cursor belongs to
# one specific record and must not be reused for other records. We therefore:
#   1) filter ASR records to one agentSessionId
#   2) extFilter AAR records to one agentChannelId
#   3) advance only that channel's activities cursor
AGENT_ACTIVITY_PAGE_QUERY = """
query(
  $from: Long!,
  $to: Long!,
  $sessionId: String!,
  $channelId: String!,
  $after: String!
) {
  agentSession(
    from: $from
    to: $to
    filter: {
      agentSessionId: { equals: $sessionId }
    }
    extFilter: {
      agentChannelId: { equals: $channelId }
    }
  ) {
    agentSessions {
      agentSessionId
      agentId
      agentName
      teamName
      startTime
      endTime
      state
      channelInfo {
        channelId
        channelType
        totalDuration
        connectedDuration
        activities(first: 100, after: $after) {
          totalCount
          pageInfo {
            endCursor
            hasNextPage
          }
          nodes {
            id
            startTime
            endTime
            state
          }
        }
      }
    }
  }
}
"""
