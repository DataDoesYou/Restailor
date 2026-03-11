/**
 * Test that validation error messages include debug information.
 * This ensures users can diagnose model selection issues without opening DevTools.
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import ResumeTailorClient from '@/components/pages/ResumeTailorClient';

// Mock next/navigation
jest.mock('next/navigation', () => ({
	useRouter: () => ({
		push: jest.fn(),
		replace: jest.fn(),
		prefetch: jest.fn(),
	}),
	useSearchParams: () => ({
		get: jest.fn(),
	}),
	usePathname: () => '/resume',
}));

// Mock fetch
global.fetch = jest.fn();

describe('Validation Error Debug Info', () => {
	beforeEach(() => {
		jest.clearAllMocks();
		(global.fetch as jest.Mock).mockResolvedValue({
			ok: true,
			json: async () => ({
				resume_text: '',
				jd_text: '',
				fit_model_id: null,
				tailor_model_id: null,
				judge_model_id: null,
			}),
		});
	});

	it('should show debug info in error message when no model is selected', async () => {
		render(<ResumeTailorClient />);

		// Wait for component to load
		await waitFor(() => {
			expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
		});

		// Add some text to pass input validation
		const resumeTextarea = screen.getByPlaceholderText(/paste.*base resume/i);
		const jdTextarea = screen.getByPlaceholderText(/paste.*job description/i);
		
		fireEvent.change(resumeTextarea, { target: { value: 'My resume text' } });
		fireEvent.change(jdTextarea, { target: { value: 'Job description text' } });

		// Try to click "Check Fit" button without selecting a model
		const checkFitButton = screen.getByText(/check fit/i);
		fireEvent.click(checkFitButton);

		// Wait for error message to appear
		await waitFor(() => {
			const errorMessage = screen.queryByText(/please select a fit model in the sidebar/i);
			expect(errorMessage).toBeInTheDocument();
		});

		// Verify debug info is included in the error message
		const errorMessage = screen.getByText(/please select a fit model in the sidebar/i);
		expect(errorMessage.textContent).toMatch(/label=NULL/);
		expect(errorMessage.textContent).toMatch(/meta=NULL/);
		expect(errorMessage.textContent).toMatch(/multi=(YES|NO)/);
	});

	it('should show label but no meta when model is partially selected', async () => {
		// Mock a scenario where we have a label but no meta (broken state)
		const mockEvent = new CustomEvent('rt-sidebar', {
			detail: { fitModelLabel: 'GPT-5.2 Instant' }
		});

		render(<ResumeTailorClient />);

		await waitFor(() => {
			expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
		});

		// Dispatch event to set label
		window.dispatchEvent(mockEvent);

		// Add resume and JD text
		const resumeTextarea = screen.getByPlaceholderText(/paste.*base resume/i);
		const jdTextarea = screen.getByPlaceholderText(/paste.*job description/i);
		
		fireEvent.change(resumeTextarea, { target: { value: 'My resume text' } });
		fireEvent.change(jdTextarea, { target: { value: 'Job description text' } });

		// Try to run
		const checkFitButton = screen.getByText(/check fit/i);
		fireEvent.click(checkFitButton);

		// Should show error with debug info showing the label but no meta
		await waitFor(() => {
			const errorMessage = screen.queryByText(/please select a fit model in the sidebar/i);
			expect(errorMessage).toBeInTheDocument();
			expect(errorMessage.textContent).toMatch(/label=GPT-5\.1 Instant/);
			expect(errorMessage.textContent).toMatch(/meta=NULL/);
		});
	});

	it('should show complete debug info when validation fails', async () => {
		render(<ResumeTailorClient />);

		await waitFor(() => {
			expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
		});

		// Add text
		const resumeTextarea = screen.getByPlaceholderText(/paste.*base resume/i);
		const jdTextarea = screen.getByPlaceholderText(/paste.*job description/i);
		
		fireEvent.change(resumeTextarea, { target: { value: 'Resume' } });
		fireEvent.change(jdTextarea, { target: { value: 'JD' } });

		// Click without model selection
		const checkFitButton = screen.getByText(/check fit/i);
		fireEvent.click(checkFitButton);

		// Verify complete debug format: (label=..., meta=..., multi=...)
		await waitFor(() => {
			const errorMessage = screen.queryByText(/please select a fit model in the sidebar/i);
			expect(errorMessage).toBeInTheDocument();
			
			// Check format: should be in parentheses with all three fields
			const text = errorMessage.textContent || '';
			expect(text).toMatch(/\(label=.*,\s*meta=.*,\s*multi=.*\)/);
		});
	});
});
