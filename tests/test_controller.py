import unittest
from unittest.mock import Mock
from controller import Controller, encode_time

class Tests(unittest.TestCase):
    def test_timer_preserves_zero_and_rejects_invalid_duration(self):
        self.assertEqual(encode_time(1, 15), '0115')
        self.assertEqual(encode_time(2, 10), '0210')
        for h,m in [(0,0),(-1,15),(1,60),(24,0)]:
            with self.assertRaises(ValueError): encode_time(h,m)

    def test_unknown_fields_cannot_be_written(self):
        c=Controller(demo=True)
        with self.assertRaises(ValueError): c.set(105, False)

    def test_sleep_and_turbo_require_cold(self):
        c=Controller(demo=True)
        c.set(4,'wind')
        for dp,value in [(25,True),(5,'strong')]:
            with self.assertRaises(ValueError): c.set(dp,value)
        c.set(4,'cold')
        self.assertTrue(c.set(25,True)['25'])
        self.assertEqual(c.set(5,'strong')['5'],'strong')

    def test_on_requires_power_off(self):
        c=Controller(demo=True)
        with self.assertRaises(ValueError): c.timer('ON',True,2,10)
        c.set(1,False)
        s=c.timer('ON',True,2,10)
        self.assertTrue(s['101'])
        self.assertEqual(s['103'],'0210')
        self.assertFalse(c.timer('ON',False)['101'])

    def test_timer_writes_disable_then_string_then_enable(self):
        c=Controller({})
        c.status=Mock(return_value={'1':False})
        device=Mock()
        device.set_value.return_value={}
        c._device=Mock(return_value=device)
        c.timer('OFF',True,1,15)
        self.assertEqual([tuple(call.args) for call in device.set_value.call_args_list], [(102,False),(104,'0115'),(102,True)])

    def test_failed_time_write_does_not_enable_timer(self):
        c=Controller({})
        c.status=Mock(return_value={'1':False})
        device=Mock()
        device.set_value.side_effect=[{}, {'Error':'failure'}]
        c._device=Mock(return_value=device)
        with self.assertRaises(RuntimeError): c.timer('OFF',True,1,15)
        self.assertEqual(device.set_value.call_count,2)

if __name__=='__main__': unittest.main()
