"""Tenant and editor readiness without browser writes or real credentials."""
import unittest
from skill6_playwright import assert_tenant, Stop

BASE = 'https://app.convertandflow.com/v2/location/FIXTURE/'


class FrameLocator:
    def __init__(self, page, name):
        self.page, self.name = page, name
    def count(self):
        return self.page.frames.get(self.name, 0)
    def wait_for(self, **kwargs):
        self.page.waits.append((self.name, kwargs))
        if self.page.on_wait:
            self.page.on_wait(self.page)
        if self.count() != 1:
            raise TimeoutError('fixture-only missing iframe')


class Workspace:
    def __init__(self, page):self.page=page
    def get_by_role(self, *args, **kwargs):return self
    def wait_for(self, **kwargs):self.page.workspace_waits += 1


class Page:
    def __init__(self, route='form-builder-v2/fixture'):
        self.url=BASE+route;self.frames={};self.waits=[]
        self.workspace_waits=0;self.on_wait=None
    def locator(self, selector):
        return FrameLocator(self, selector.split('name="')[1].split('"')[0])
    def get_by_role(self, *args, **kwargs):
        return Workspace(self)


def job(page):
    return {'location_id':'FIXTURE','location_name':'Fixture','start_url':page.url}


class EditorHydrationTests(unittest.TestCase):
    def test_delayed_expected_iframe_never_uses_dashboard_guard(self):
        for route, expected in (('form-builder-v2/form','form-builder-app'),
            ('survey-builder-v2/survey','survey-builder-app'),
            ('quiz-builder-v2/quiz','quiz-builder-app'),
            ('page-builder/page','funnel-builder')):
            with self.subTest(route=route):
                page=Page(route)
                page.on_wait=lambda current:current.frames.update({expected:1})
                assert_tenant(page,job(page))
                self.assertEqual(page.waits,[(expected,{'state':'visible','timeout':45000})])
                self.assertEqual(page.workspace_waits,0)

    def test_wrong_tenant_during_hydration_fails_before_any_editor_action(self):
        page=Page(); original=job(page)
        def navigate(current):
            current.url=current.url.replace('/FIXTURE/','/OTHER/')
            current.frames['form-builder-app']=1
        page.on_wait=navigate
        with self.assertRaisesRegex(Stop,'Wrong tenant'):
            assert_tenant(page,original)
        self.assertEqual(page.workspace_waits,0)

    def test_wrong_origin_or_builder_route_during_hydration_is_rejected(self):
        for url in ('http://app.convertandflow.com/v2/location/FIXTURE/form-builder-v2/form',
                    'https://untrusted.invalid/v2/location/FIXTURE/form-builder-v2/form',
                    BASE+'quiz-builder-v2/quiz'):
            with self.subTest(url=url):
                page=Page(); original=job(page)
                def navigate(current):
                    current.url=url;current.frames['form-builder-app']=1
                page.on_wait=navigate
                with self.assertRaises(Stop):assert_tenant(page,original)
                self.assertEqual(page.workspace_waits,0)

    def test_wrong_or_ambiguous_builder_iframe_fails_without_dashboard_wait(self):
        for frames in ({'quiz-builder-app':1},{'form-builder-app':2},
                       {'form-builder-app':1,'survey-builder-app':1}):
            with self.subTest(frames=frames):
                page=Page();page.frames=frames
                with self.assertRaises(Stop):assert_tenant(page,job(page))
                self.assertEqual(page.workspace_waits,0)
                self.assertEqual(page.waits,[])

    def test_missing_expected_iframe_never_falls_back_to_dashboard(self):
        page=Page()
        with self.assertRaisesRegex(Stop,'did not hydrate'):
            assert_tenant(page,job(page))
        self.assertEqual(page.workspace_waits,0)

    def test_dashboard_still_requires_visible_named_workspace(self):
        page=Page('dashboard');page.frames['form-builder-app']=1
        assert_tenant(page,job(page))
        self.assertEqual(page.workspace_waits,1)
        self.assertEqual(page.waits,[])


if __name__=='__main__':unittest.main()
