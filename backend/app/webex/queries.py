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

AGENT_SESSION_QUERY = """
query($from: Long!, $to: Long!, $after: String) {
  agentSession(from: $from, to: $to) {
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
        activities(after: $after) {
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
