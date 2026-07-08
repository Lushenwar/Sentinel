import { render, screen } from "@testing-library/react";
import IncidentFeed from "@/app/page";
import { DiffViewer } from "@/components/DiffViewer";
import { PostmortemEditor } from "@/components/PostmortemEditor";

jest.mock("@/lib/api", () => ({
  listIncidents: jest.fn().mockResolvedValue([
    {
      id: "inc_2026_0708_test",
      status: "triaging",
      trigger_data: {
        alert_name: "HTTP_500_Internal_Server_Error",
        timestamp: "2026-07-08T00:00:00Z",
        error_signature: "OperationalError: connection refused",
      },
    },
  ]),
  getCommitDiff: jest.fn(),
  savePostmortem: jest.fn(),
}));

test("incident feed renders a list of incidents", async () => {
  render(<IncidentFeed />);
  expect(await screen.findByText("inc_2026_0708_test")).toBeInTheDocument();
  expect(screen.getByText("triaging")).toBeInTheDocument();
});

test("diff viewer mounts with its toggle button", () => {
  render(<DiffViewer incidentId="inc_x" commitHash="a1b2c3d" />);
  expect(screen.getByRole("button", { name: "View diff" })).toBeInTheDocument();
});

test("postmortem editor loads initial content", () => {
  render(<PostmortemEditor incidentId="inc_x" initial="## Summary of the incident" />);
  expect(screen.getByTestId("markdown")).toHaveTextContent("Summary of the incident");
  expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
});
